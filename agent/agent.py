import logging

import pandas as pd

from .tools.base_knowledge.get_base_knowledge import BASE, TARGET
from .tools.copilot.utils.code_insert import insert_lines_into_function
from .tools.tools_def import engine, llm, query_database, exe_sql

from .tools.copilot.python_code import get_py_code
from .tools.copilot.utils.code_executor import execute_py_code
from .tools.copilot.sql_code import get_db_info_prompt, filter_db_fields
from .tools.copilot.utils.call_llm_test import call_llm_stream
from .tools.copilot.utils.parse_output import parse_generated_python_code

from .tools.get_function_info import get_function_info, FUNCTION_DICT, FUNCTION_IMPORT, ASSIST_FUNCTION_DICT, IMPORTANT_FUNC

from .utils.final_output_parse import df_to_markdown, wrap_html_url_with_html_a, \
    wrap_csv_url_with_html_a, is_local_png_path
from .utils.final_output_parse import wrap_png_url_with_markdown_image, is_png_url, is_iframe_tag
from .utils.get_config import config_data
from .utils.pd_to_csv import pd_to_csv
from .utils.pd_to_walker import pd_to_walker

STATIC_URL = config_data['static_path']

IMPORTANT_MODULE = ["import math"]
THIRD_MODULE = ["import pandas as pd", "import numpy as np",
                "import PIL", "import matplotlib",
                "matplotlib.use('Agg')",
                "import matplotlib.pyplot as plt", "import seaborn as sns"]

# print(get_db_info_prompt(engine, simple=True, example=False))


def get_db():
    return get_db_info_prompt(engine, example=True, simple=True)


def get_cot_code_prompt(question, tables=None, selected_fields=None, selected_functions=None):
    rag_ans = ""
    knowledge = ""
    knowledge = BASE + "\n" + TARGET
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
        function_set, function_info, function_import = get_function_info(question, llm, use_all_functions=True)

    database = ""
    if query_database in function_set or exe_sql in function_set:
        if selected_fields and selected_fields.get("__no_db__"):
            database = ""
        else:
            data_prompt = get_db_info_prompt(engine, tables=tables, simple=True, example=False, selected_fields=selected_fields)
            database = "\nThe database content: \n" + data_prompt + "\n"

    pre_prompt = """ 
Please use the following functions to solve the problem.
"""
    function_prompt = """ 
Here is the functions you can import and use:
"""
    module_prompt = "You can only use the third party function in " + str(THIRD_MODULE) + " !!!"

    example_code = """
    Here is an example: 
    ```python
    def func():
        import math
        import pandas as pd
        import numpy as np
        import PIL
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import seaborn as sns
        # generate code to perform operations from here

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

    ⚠️ LANGUAGE — READ THIS FIRST: Before writing any code, check the user's original question language. ALL your output text (yield messages, chart titles, axis labels, legends, annotations, explanations, error messages, and any user-facing text) MUST be in the EXACT SAME language as the user's original question. If the user asked in Chinese, you MUST write ALL text in Chinese. If the user asked in English, you MUST write ALL text in English. This is NOT a suggestion — it is a HARD REQUIREMENT. The context, database content, and knowledge base may contain mixed languages — they are for factual content ONLY. Their language must NEVER leak into your yield text, chart labels, or any output. Every word of user-facing text you generate must be in the user's language. VIOLATING THIS RULE IS A CRITICAL ERROR.

    ⚠️ CRITICAL OUTPUT FORMAT — VIOLATION WILL CAUSE EXECUTION FAILURE:
    - Your ENTIRE response MUST be wrapped in a SINGLE ```python ... ``` markdown code block. Nothing outside the code block is allowed.
    - The first line of your code MUST be `def func():`. Do NOT write any code, text, or explanation outside the function.
    - Even if the question can be answered with plain text only (no function calls, no data queries), you MUST still generate code in the ```python``` block format. Use `yield "your answer text"` to output the answer.
    - NEVER output plain text outside the code block. NEVER output markdown, explanations, or conversational text before or after the code block.
    
    Wrong format (will be rejected):
    - Outputting: "The answer is 42" (plain text, no code block)
    - Outputting: ```python\ndef func():\n    yield "hello"\n```\nHere is some extra text... (text outside code block)
    - Outputting: Let me think...\n```python\ndef func():\n    ...\n``` (text before code block)
    
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
    
    **Todo List Execution Rule (Strictly Enforced)**:
    - If a todo list exists in the context, you MUST execute ONLY the **first incomplete task** on the list.
    - Stop immediately after completing that task, waiting for the next call.
    - **DO NOT** execute multiple todo items at once, even if they seem simple.
    - **DO NOT** skip or pre-execute later tasks.
    - If the current todo item requires user confirmation or additional information, yield the request and stop. Do NOT proceed to other items.
    """

    final_language_check = """
⚠️ FINAL LANGUAGE CHECK: The knowledge base above is in Chinese — IGNORE THAT. All your output text MUST be in the user's language. Check the user's question now: what language is it in? Write ALL text (yield messages, chart titles, labels) in that language. Do NOT copy the knowledge base's language.
"""

    cot_prompt = pre_prompt + function_prompt + str(function_info) + \
                 module_prompt + example_code + remind_prompt + \
                 database + knowledge + " \nContext:\n" + question + \
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
        html_link = pd_to_walker(item)
        csv_link = pd_to_csv(item)
        text += wrap_html_url_with_html_a(html_link)
        text += wrap_csv_url_with_html_a(csv_link)
        return text
    elif isinstance(item, str) and is_png_url(item):
        return "\n" + wrap_png_url_with_markdown_image(item) + "\n"
    elif isinstance(item, str) and is_local_png_path(item):
        return "\n" + wrap_png_url_with_markdown_image(STATIC_URL + item[2:]) + "\n"
    elif is_iframe_tag(str(item)):
        return "\n" + str(item) + "\n"
    else:
        return "\n" + str(item) + "\n"


def generate_and_execute_stream(question, tables=None, retries=2,
                                 selected_fields=None, selected_functions=None, print_rows=5,
                                 ):
    yield {"type": "msg", "content": "正在分析问题...", "phase": "act", "sub_phase": "code"}

    cot_prompt, rag_ans, function_import = get_cot_code_prompt(question, tables, selected_fields, selected_functions)
    prompt_length = len(cot_prompt)

    error_msg = ""

    for i in range(retries):
        if i > 0:
            yield {"type": "msg", "content": "执行出错，正在根据错误信息重新生成代码...", "phase": "act", "sub_phase": "code"}
        else:
            yield {"type": "msg", "content": "正在生成代码...", "phase": "act", "sub_phase": "code"}

        full_prompt = cot_prompt + error_msg
        raw_content = ""
        for chunk in call_llm_stream(full_prompt, llm):
            raw_content += chunk
            yield {"type": "chunk", "sub_type": "code_chunk", "content": chunk, "phase": "act", "sub_phase": "code"}

        code = parse_generated_python_code(raw_content)
        if code is None:
            yield {"type": "chunk", "sub_type": "code_gen_error", "content": "code generation error", "phase": "act", "sub_phase": "code"}
            error_msg = """
        code should only be in a md code block: 
        ```python
        def func(data_dict):
            import pandas as pd
            import math
            # some python code
            # access dataframes like: df1 = data_dict['key1']
        without any additional comments, explanations or cmds !!!
        """
            continue

        code = insert_lines_into_function(code, function_import)
        code = insert_lines_into_function(code, IMPORTANT_MODULE)
        code = insert_lines_into_function(code, THIRD_MODULE)
        # code += " err test "
        # print("\n[Generated Code]:\n", code)

        yield {"type": "chunk", "sub_type": "code_complete", "content": code, "phase": "act", "sub_phase": "code"}

        yield {"type": "msg", "content": "正在执行代码...", "phase": "act", "sub_phase": "exec"}

        error_msg = ""
        formatted_result = ""
        try:
            result = execute_py_code(code)
            for item in result:
                formatted = format_yield_item(item, print_rows)
                formatted_result += formatted
                formatted_result += "\n"
                yield {"type": "chunk", "sub_type": "exec_chunk", "content": formatted, "phase": "act", "sub_phase": "exec"}
        except Exception as e:
            error_msg = str(e)
            print(f"Execution error: {e}")
            yield {"type": "chunk", "sub_type": "code_exe_error", "content": error_msg, "phase": "act", "sub_phase": "exec"}
            continue

        yield {"type": "chunk", "sub_type": "exec_complete", "content": formatted_result, "phase": "act", "sub_phase": "exec"}
        yield {"type": "done", "code": code, "content": formatted_result, "phase": "act", "sub_phase": "exec"}
        return

    yield {"type": "error", "content": "generate_and_execute_stream_error", "phase": "act"}

