import logging
import os
import re
import time as _time

import pandas as pd

from .tools.base_knowledge.get_base_knowledge import BASE_MD, TARGET, get_code_guide_db, get_graph_code_guide_db, base_knowledge_to_str
from .tools.copilot.utils.code_insert import insert_lines_into_function
from .tools.tools_def import engine, llm, exe_sql, read_only_engine

from .tools.copilot.utils.code_executor import execute_py_code
# Single source of truth for the module allow-list promised by the code-gen
# prompt below; keeps prompt, injected imports and sandbox policy in sync.
from .tools.copilot.utils.sandbox.policy import ALLOWED_MODULE_ROOTS
from .tools.copilot.sql_code import get_db_info_prompt
from .tools.copilot.utils.parse_output import parse_generated_python_code
from utils.perf_log import record_code_exec

from .tools.get_function_info import get_function_info, FUNCTION_DICT, FUNCTION_IMPORT, ASSIST_FUNCTION_DICT, IMPORTANT_FUNC

from .utils.final_output_parse import df_to_markdown, wrap_html_url_with_html_a, \
    wrap_csv_url_with_html_a, is_local_png_path
from .utils.final_output_parse import wrap_png_url_with_markdown_image, is_png_url, is_iframe_tag
from .utils.get_config import config_data
from .utils.pd_to_csv import pd_to_csv
from .utils.pd_to_walker import pd_to_walker
from utils.blackboard import blackboard_to_text, blackboard_input_images, FUNCTIONS
from utils.context_trim import cap_text, stream_with_context_retry

STATIC_URL = config_data['static_path']

# Matches a link to a local ``tmp_imgs`` image served from this project's own
# ``static_path`` (e.g. ``http://127.0.0.1:8008/tmp_imgs/xxx.png``). The char class
# stops at whitespace/quotes/brackets so a URL inside markdown ``](...)`` or an
# HTML attribute is captured cleanly.
_OWN_STATIC_IMAGE_RE = re.compile(
    re.escape(STATIC_URL.rstrip("/")) + r"/tmp_imgs/[^\s\"'<>()]+\.png",
    re.IGNORECASE,
)


def _auto_attach_local_images(item: str):
    """Return the local ``tmp_imgs`` basename(s) for a yielded image item.

    Only images that live in the local ``tmp_imgs`` directory are auto-attached to
    later LLM calls: a yielded local path (``./tmp_imgs/x.png``) or a link to
    ``tmp_imgs`` served from this project's own ``static_path``. Arbitrary external
    image URLs are NEVER captured here, because untrusted content (web pages, MCP
    results, database text) could otherwise plant an image URL that is silently fed
    to the model. Such images still appear in the yielded text for the user and can
    be attached on purpose through the ``select_images`` action.
    """
    if not isinstance(item, str):
        return []
    if is_local_png_path(item):
        return [os.path.basename(item)]
    return [os.path.basename(url) for url in _OWN_STATIC_IMAGE_RE.findall(item)]


# `func` runs inside the sandbox subprocess, which already configures the Chinese
# font and the Agg backend at startup, so no font import/setup is injected here and
# `os` is intentionally NOT injected (it is blocked by the sandbox policy).
IMPORTANT_MODULE = ["import math"]
THIRD_MODULE = ["import pandas as pd", "import numpy as np",
                "import PIL", "import matplotlib",
                "matplotlib.use('Agg')",
                "import matplotlib.pyplot as plt", "import seaborn as sns",
                "import json", "import re", "import datetime",
                "import textwrap", "import random",
                "import collections", "import io", "import functools",
                "import itertools", "import statistics", "import decimal",
                "import fractions", "import uuid", "import string",
                "import copy", "import typing", "import warnings",
                "import numbers"]

# The code-gen prompt promises exactly the modules injected into `func`, and the
# sandbox policy allow-list must match both: a module promised but not injected
# raises NameError at runtime, while one injected but not allowed is rejected by
# the policy. Warn loudly if the lists ever drift apart.
_INJECTED_MODULE_ROOTS = set()
for _line in IMPORTANT_MODULE + THIRD_MODULE:
    _parts = _line.split()
    if len(_parts) >= 2 and _parts[0] in ("import", "from"):
        _INJECTED_MODULE_ROOTS.add(_parts[1].split(".")[0])
if _INJECTED_MODULE_ROOTS != ALLOWED_MODULE_ROOTS:
    print(
        "[WARNING] Injected code-gen module imports do not match the sandbox "
        "policy ALLOWED_MODULE_ROOTS; "
        f"missing={sorted(ALLOWED_MODULE_ROOTS - _INJECTED_MODULE_ROOTS)} "
        f"extra={sorted(_INJECTED_MODULE_ROOTS - ALLOWED_MODULE_ROOTS)}"
    )

# print(get_db_info_prompt(engine, simple=True, example=False))


def get_db():
    return get_db_info_prompt(read_only_engine, example=True, simple=True)


# `context_text` is the text rendered into the prompt's final "Context:" block.
# The act pipeline passes the already-rendered conversation history; direct API
# callers of /api/generate-and-execute/stream/ (whose AgentInput has no
# conversation_history field) may pass a raw question instead.
def get_cot_code_prompt(context_text, tables=None, selected_fields=None, selected_functions=None, research_guide=None,
                        blackboard=None, level=0):
    blackboard = blackboard or {}
    board_schema = blackboard.get("schema") or {}
    board_functions = blackboard.get("functions") or {}

    board_selected_functions = board_functions.get("selected_functions")
    if isinstance(board_selected_functions, list) and board_selected_functions:
        selected_functions = board_selected_functions

    # An empty selection (a failed explore_functions that wrote an empty list,
    # or a legacy poisoned blackboard) must NOT blank out the function catalog
    # and DB schema. Treat it as "no explicit selection" and fall back to the
    # full function set, otherwise code generation runs with no tools and no
    # database structure at all.
    if selected_functions is not None and not selected_functions:
        selected_functions = None

    rag_ans = ""
    # The KNOWLEDGE blackboard region (written by `explore_base_knowledge`) is the
    # single source of base knowledge for this phase; its selected entries are
    # injected via `blackboard_text` below. Injecting the full `base_knowledge`
    # table here would duplicate them, so only `base_knowledge.md` (never offered
    # to `explore_base_knowledge`) is injected here.
    knowledge = str(BASE_MD) + "\n" if str(BASE_MD).strip() else ""
    code_guide_data = get_code_guide_db()
    if code_guide_data:
        knowledge += "\nCode Guide:\n" + base_knowledge_to_str(code_guide_data) + "\n"
    graph_code_guide_data = get_graph_code_guide_db()
    if graph_code_guide_data:
        knowledge += "\nGraph Code Guide:\n" + base_knowledge_to_str(graph_code_guide_data) + "\n"
    blackboard_text = ""
    if blackboard:
        # `function_info` below already carries the selected functions'
        # docstrings, so the FUNC region's short `func_docs` is redundant here.
        bb = blackboard_to_text(blackboard, level=level, omit_fields={FUNCTIONS: ("func_docs",)})
        if bb:
            blackboard_text = "\n\n## Blackboard\n\n" + bb + "\n"

    target_section = ""
    if config_data.get('enable_target_knowledge', False) and TARGET.strip() != "":
        target_section = "The target document template below defines the data and charts that the final report must contain. Your generated code MUST query the necessary data and produce the required charts/images to fulfill this template:\n\n" + TARGET + "\n"
    # print(rag_ans)

    if selected_functions is not None:
        function_set = set()
        function_info = ""
        function_import = []
        for func_name in selected_functions:
            func = FUNCTION_DICT.get(func_name)
            if func:
                function_set.add(func)
                assist_functions = ASSIST_FUNCTION_DICT.get(func)
                if assist_functions:
                    for assist_function in assist_functions:
                        function_set.add(assist_function)
        for main_function in selected_functions:
            assist_functions = ASSIST_FUNCTION_DICT.get(main_function)
            if assist_functions:
                for assist_function in assist_functions:
                    function_set.add(assist_function)
        for func_name in IMPORTANT_FUNC:
            func = FUNCTION_DICT.get(func_name)
            if func:
                function_set.add(func)
        for function in function_set:
            function_info += "\n" + str(function.__doc__) + "\n"
            import_list = FUNCTION_IMPORT.get(function)
            if import_list:
                function_import.append(import_list)
    else:
        function_set, function_info, function_import = get_function_info(context_text, llm, use_all_functions=True)

    if selected_fields is None:
        board_selected_fields = board_schema.get("selected_fields")
        if isinstance(board_selected_fields, dict):
            selected_fields = board_selected_fields

    database = ""
    if exe_sql in function_set:
        if selected_fields and selected_fields.get("__no_db__"):
            database = ""
        elif board_schema.get("schema_detail"):
            database = ""
        else:
            data_prompt = get_db_info_prompt(read_only_engine, tables=tables, simple=True, example=False, selected_fields=selected_fields)
            database = "\nThe database content: \n" + data_prompt + "\n"

    pre_prompt = """ 
Please use the following functions to write Python code to solve the problem.
"""
    function_prompt = """ 
Here are the functions you can call directly (do NOT import them):
"""
    available_import_lines = IMPORTANT_MODULE + THIRD_MODULE
    allowed_modules_str = ", ".join(sorted(ALLOWED_MODULE_ROOTS))
    module_prompt = f"""
PRE-IMPORTED MODULES (READ THIS FIRST):
Your generated code MUST NOT write ANY import statement (e.g. do NOT write `import pandas as pd`), MUST NOT re-import any of these modules, and MUST NOT import or use ANY module other than the ALLOWED MODULES listed below.
How the modules are provided for you (you never need to import anything yourself):
- ALL allowed modules are made available by the import/setup lines shown below, which the system injects automatically into your code after generation.
- In sandboxed execution the runtime additionally pre-initializes the common ones (pd, np, plt, sns, PIL, math, json, re, datetime, matplotlib) before your code runs.

Import/setup lines injected automatically:
{chr(10).join(available_import_lines)}

ALLOWED MODULES (use ONLY these): {allowed_modules_str}.
Any module outside this list (e.g. os, sys, subprocess, requests, urllib, socket) is blocked by the execution policy and will fail with an error.
"""

    example_code = """
    Here is an example: 
    ```python
    def func():
        yield "A01 class's grades are as follows:"  # yield some information and explanation
        yield "use table: stu_info ,stu_grade"  # yield tables names before query database function
        df = exe_sql(\"\"\"
            SELECT s.student_id, s.name, g.course, g.score FROM stu_info s
            JOIN stu_grade g ON s.student_id = g.student_id
            WHERE s.class = 'A01'
        \"\"\")   
        yield df # the result of each step and function call
        # None or empty DataFrame return handling for each function call.
        if df is None or df.empty:
            yield "The grades for this class were not found in the database"
            return

        # IMPORTANT: Handle too many categories BEFORE plotting
        unique_categories = df['course'].nunique()
        if unique_categories > 10:
            yield f"Due to too many courses ({unique_categories}), only the first 10 items are displayed. Please modify your question if you want to see specific items, e.g., 'show only the top 5' or 'show only courses A, B, C'."
            # Get top 10 most frequent courses
            top_courses = df['course'].value_counts().head(10).index.tolist()
            df = df[df['course'].isin(top_courses)]

        yield "The grade histogram is as follows:"
        plt.figure(figsize=(8, 5))
        plt.hist(df['score'], bins=8, edgecolor='black', alpha=0.7, color='steelblue')
        plt.xlabel('Score')
        plt.ylabel('Number of Students')
        plt.title('A01 Class Grade Distribution')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout() # must use after rotation
        plt.grid(axis='y', alpha=0.3)
        path = get_save_image_path()
        plt.savefig(path, dpi=150, bbox_inches='tight')
        plt.close()
        yield path
    ```
    """

    remind_prompt = """
    Remind: 

    ⚠️ LANGUAGE — READ THIS FIRST: Before writing any code, check the user's original question language. All the prose and labels YOU author (yield messages, chart titles, axis titles, legends, annotations, explanations, error messages, and other user-facing text) MUST be in the EXACT SAME language as the user's original question. If the user asked in Chinese, you MUST write this authored text in Chinese. If the user asked in English, you MUST write this authored text in English. This is NOT a suggestion — it is a HARD REQUIREMENT. The context, database content, and knowledge base may contain mixed languages — they are for factual content ONLY. Their language must NEVER leak into the prose you author. IMPORTANT: table names, column names, and the data values taken from the query result (including the category and tick labels plotted from that data, such as town or flat-model names) keep their original language and MUST NOT be translated; only the text you author around them follows the user's language. VIOLATING THIS RULE IS A CRITICAL ERROR.

    ⚠️ CRITICAL OUTPUT FORMAT — VIOLATION WILL CAUSE EXECUTION FAILURE:
    - Your ENTIRE response MUST be wrapped in a SINGLE ```python ... ``` markdown code block. Nothing outside the code block is allowed.
    - Your code MUST contain `def func():` (i.e. define a function named `func`). Do NOT write any code, text, or explanation outside the function.
    - DO NOT write ANY import statement in your code (e.g. do NOT write `import pandas as pd`, `from agent.tools.tools_def import ...`, `from agent.tools.custom_tools_def import ...`, etc.). All necessary imports — including the provided functions (exe_sql, load_data, explain_data, get_save_image_path, exe_mcp, predict_hdb_price, etc.) and third-party modules (pandas, numpy, matplotlib, PIL, etc.) — are ALREADY available and will be injected automatically after your code is generated. Just call them directly.
    - Even if the question can be answered with plain text only (no function calls, no data queries), you MUST still generate code in the ```python``` block format. Use `yield "your answer text"` to output the answer.
    - NEVER output plain text outside the code block. NEVER output markdown, explanations, or conversational text before or after the code block.
    - NEVER write any python code outside the code block. NEVER output the code twice — only the single code block content.
    
    Correct format for text-only answers:
    ```python
    def func():
        yield "Your answer text here"
    ```

    - IMPORTANT: Please use yield instead of return and print(), never use input() or any funcs that hung up the process to wait user action!
    - Please yield explanation string of each step as kind of report! Please yield some information string during the function!
    - Please yield the result of each step and function call! Please yield report many times during the function!!! not only yield at last! 
    - Please yield the tables used before query database function!!!
    - If the user just ask to introduce or explain something, just yield the answer text in code without function call.
    - None or empty DataFrame return handling for each function call is extremely important!
    
    You may draw some graphs with the given third party module.

    - IMPORTANT: Please save the image instead of show it, never use any funcs that hung up the process to wait user action!
    - you can save it only with generated file path: `path = get_save_image_path()`!!!
    - use different path to save different image, `get_save_image_path()` return a unique path each time you call it.
    - yield the path with single line :`yield path` , never yield the path in other str or tuple.

    - CRITICAL: Category Overflow Handling (MUST DO BEFORE PLOTTING):
      1. BEFORE creating ANY chart with categorical labels (pie, bar, barh, boxplot, line, scatter, heatmap, radar, etc.), 
         check the number of unique categories that will appear as labels.
      2. If categories > 10, you MUST:
         a) First yield a message: "⚠️ Due to too many categories ({N} found), only the first/top 10 items are displayed. 
            Please modify your question if you want to see specific items, e.g., 'show only the top 5' or 'show only categories A, B, C'."
         b) THEN filter the data to keep only top 10 (by count/frequency) or first 10
         c) ONLY AFTER filtering, create the plot
      3. For pie charts specifically:
         - If categories > 5, consider using "explode" to highlight key slices
         - If categories > 8, consider using "wedgeprops" to increase spacing
         - Always show percentages instead of raw values for readability
      4. For labels that are still long after filtering:
         - Rotate labels: plt.xticks(rotation=45) or plt.xticks(rotation=90)
         - Use abbreviations or wrap text (e.g., '\n'.join(textwrap.wrap(label, 10)))
         - For pie charts, use legend instead of direct labels when categories > 5
      5. NEVER skip filtering and go directly to rotation/abbreviation - 
         that only masks the problem without solving overcrowding!
        Data Standardization and Entity Alignment.

    - The user's query terms may NOT match the actual values stored in the database. You MUST handle this mismatch:
        1. BEFORE querying, check the actual values in the database using DISTINCT or sample queries to understand the data format
        2. Use case-insensitive matching (e.g., LOWER() or UPPER() functions in SQL, or .str.lower() in pandas)
        3. Use pattern matching (e.g., LIKE '%china%', regex) when exact match fails
        4. Handle common variations:
           - Countries: 'China' may be stored as 'chn', 'CHN', 'PRC', 'CN', 'Mainland China', '中国'
           - Gender: 'male'/'female' may be 'M'/'F', 'm'/'f', '1'/'0', '男'/'女'
           - Yes/No: may be 'Y'/'N', 'true'/'false', '1'/'0', '是'/'否'
           - Abbreviations: 'USA'/'US'/'United States', 'UK'/'United Kingdom'/'GB'
           - and others ...
        5. If uncertain about the exact format, query for distinct values first and show them to the user for confirmation
        6. Yield a message explaining any standardization decisions made (e.g., "Searching for 'China' matched database values: 'CHN', 'PRC'")
    
    **Todo List Execution Rule**:
    - If a todo list exists in the context, you MUST execute ONLY the **first incomplete task** on the list.
    - **DO NOT** execute multiple todo items at once, even if they seem simple.
    - **DO NOT** skip or pre-execute later tasks.
    - If the current todo item requires user confirmation or additional information, yield the request and stop. Do NOT proceed to other items.
    """

    final_language_check = """
"""

    research_section = ""
    if research_guide:
        research_section = "\n\nImage and Data Requirements:\n" + research_guide + "\n\nYou MUST query the data and generate the images described above. Include the generated image paths in your output using `yield path`."

    if level > 0:
        function_info = cap_text(function_info, level)
        database = cap_text(database, level)
        knowledge = cap_text(knowledge, level)
        context_text = cap_text(context_text, level)

    cot_prompt = pre_prompt + function_prompt + str(function_info) + \
                 module_prompt + example_code + remind_prompt + \
                 database + knowledge + blackboard_text + target_section + research_section + " \nContext:\n" + context_text + \
                 final_language_check
    return cot_prompt, rag_ans, function_import


def format_yield_item(item, print_rows=5):
    if isinstance(item, pd.DataFrame):
        if item.index.size > 50:
            text = df_to_markdown(item.head(print_rows)) + \
                   "\nfirst {} rows of {}".format(print_rows, len(item)) + \
                   "\nthe data above are just slice example, download csv to get full data\n"
        else:
            text = df_to_markdown(item)
        attrs = getattr(item, "attrs", None) or {}
        if attrs.get("sandbox_truncated"):
            original_rows = attrs.get("sandbox_original_rows")
            original = f" (original rows: {original_rows})" if original_rows is not None else ""
            text = (
                "\n⚠️ The result was truncated by the execution sandbox"
                f"{original}; only part of the data was transferred. Please narrow "
                "the query (WHERE / LIMIT) if the full data is needed.\n"
            ) + text
        html_link = pd_to_walker(item)
        csv_link = pd_to_csv(item)
        text += wrap_html_url_with_html_a(html_link)
        text += wrap_csv_url_with_html_a(csv_link)
        return text
    elif is_iframe_tag(str(item)):
        return "\n" + str(item) + "\n"
    elif isinstance(item, str) and is_png_url(item):
        return "\n" + wrap_png_url_with_markdown_image(item) + "\n"
    elif isinstance(item, str) and is_local_png_path(item):
        return "\n" + wrap_png_url_with_markdown_image(STATIC_URL + item[2:]) + "\n"
    else:
        return "\n" + str(item) + "\n"


# `context_text` is injected as the prompt's final "Context:" block (see
# `get_cot_code_prompt`). The act pipeline passes the rendered conversation
# history; direct API callers may pass a raw question. `question_builder`, when
# given, rebuilds that text for each context-trim level.
def generate_and_execute_stream(context_text, tables=None, retries=2,
                                 selected_fields=None, selected_functions=None, print_rows=5,
                                 research_guide=None, blackboard=None, images=None,
                                 question_builder=None, session_id="",
                                 ):
    yield {"type": "msg", "content": "Analyzing question...", "phase": "act", "sub_phase": "code"}

    cot_prompt, rag_ans, function_import = get_cot_code_prompt(
        context_text, tables, selected_fields, selected_functions, research_guide, blackboard)
    prompt_length = len(cot_prompt)
    input_images = images
    if input_images is None and blackboard:
        input_images = blackboard_input_images(blackboard)

    def build_prompt(level):
        q = question_builder(level) if question_builder else context_text
        cot, _, _ = get_cot_code_prompt(
            q, tables, selected_fields, selected_functions, research_guide, blackboard, level=level)
        return cot

    error_msg = ""
    # Machine-readable failure code and its raw detail, carried out of the retry
    # loop so the terminal error event can record and forward exactly what failed
    # (instead of a generic "generate_and_execute_stream_error").
    error_kind = ""
    error_detail = ""

    for i in range(retries):
        if i > 0:
            yield {"type": "msg", "content": "Execution failed, regenerating code based on error...", "phase": "act", "sub_phase": "code"}
        else:
            yield {"type": "msg", "content": "Generating code...", "phase": "act", "sub_phase": "code"}

        full_prompt = cot_prompt + error_msg
        raw_content = ""
        for chunk, reasoning in stream_with_context_retry(lambda lvl: build_prompt(lvl) + error_msg, llm, images=input_images):
            if chunk:
                raw_content += chunk
                yield {"type": "chunk", "sub_type": "code_chunk", "content": chunk, "phase": "act", "sub_phase": "code"}
            if reasoning:
                yield {"type": "reasoning_chunk", "content": reasoning, "phase": "act", "sub_phase": "code"}

        code = parse_generated_python_code(raw_content)
        if code is None:
            error_kind = "code_format_error"
            error_detail = "code generation error"
            yield {"type": "chunk", "sub_type": "code_gen_error", "content": "code generation error", "error_kind": error_kind, "phase": "act", "sub_phase": "code"}
            error_msg = """
        code should only be in a md code block: 
        ```python
        def func():
            # some python code
        ```
        without any additional comments, explanations or cmds !!!
        DO NOT write any import statement in your code, all imports will be injected automatically.
        """
            continue

        if 'def func(' not in code:
            error_kind = "no_func"
            error_detail = "def func not found"
            yield {"type": "chunk", "sub_type": "code_gen_error", "content": "def func not found", "error_kind": error_kind, "phase": "act", "sub_phase": "code"}
            error_msg = """
        The code must define a function named `func`, i.e. contain `def func():`. 
        Do NOT write any code, text, or explanation outside the function.
        ```python
        def func():
            # some python code
        ```
        without any additional comments, explanations or cmds !!!
        """
            continue

        # Privileged tool imports (`from agent.tools... import ...`) are no longer
        # injected: the sandbox namespace already provides the whitelisted tool
        # functions, and such imports are rejected by the sandbox policy anyway.
        code = insert_lines_into_function(code, IMPORTANT_MODULE)
        code = insert_lines_into_function(code, THIRD_MODULE)
        # code += " err test "
        # print("\n[Generated Code]:\n", code)

        yield {"type": "chunk", "sub_type": "code_complete", "content": code, "phase": "act", "sub_phase": "code"}

        yield {"type": "msg", "content": "Executing code...", "phase": "act", "sub_phase": "exec"}

        error_msg = ""
        formatted_result = ""
        images = []
        _exec_start = _time.monotonic()
        try:
            result = execute_py_code(code, session_id=session_id)
            for item in result:
                formatted = format_yield_item(item, print_rows)
                formatted_result += formatted
                formatted_result += "\n"
                if isinstance(item, str):
                    # Auto-attach only trusted local tmp_imgs images; external
                    # image URLs are not silently fed to the model (see
                    # _auto_attach_local_images).
                    images.extend(_auto_attach_local_images(item))
                yield {"type": "chunk", "sub_type": "exec_chunk", "content": formatted, "phase": "act", "sub_phase": "exec"}
        except Exception as e:
            error_kind = getattr(e, "kind", "execution_error")
            error_detail = str(e)
            error_msg = f"[{error_kind}] {e}"
            print(f"Execution error ({error_kind}): {e}")
            yield {"type": "chunk", "sub_type": "code_exe_error", "content": error_detail, "error_kind": error_kind, "phase": "act", "sub_phase": "exec"}
            continue
        finally:
            record_code_exec(_time.monotonic() - _exec_start)

        seen = set()
        images = [u for u in images if not (u in seen or seen.add(u))]

        yield {"type": "chunk", "sub_type": "exec_complete", "content": formatted_result, "phase": "act", "sub_phase": "exec", "images": images}
        yield {"type": "done", "code": code, "content": formatted_result, "phase": "act", "sub_phase": "exec", "images": images}
        return

    # Retry budget exhausted: emit a terminal, actionable error that carries the
    # concrete failure kind and detail. ``sub_phase`` is set so the client treats
    # it as a handled action failure (recorded, fed to the next LLM step) rather
    # than a transport failure.
    final_kind = error_kind or "execution_error"
    final_detail = error_detail or "code generation/execution failed"
    yield {
        "type": "error",
        "content": "generate_and_execute_stream_error",
        "error_kind": final_kind,
        "error": final_detail,
        "phase": "act",
        "sub_phase": "exec",
    }

