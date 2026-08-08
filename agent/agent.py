import logging

import pandas as pd

from .tools.base_knowledge.get_base_knowledge import get_base_knowledge
from .tools.copilot.utils.code_insert import insert_lines_into_function
from .tools.tools_def import engine, llm, query_database, exe_sql

from .tools.copilot.python_code import get_py_code
from .tools.copilot.utils.code_executor import execute_py_code
from .tools.copilot.sql_code import get_db_info_prompt, filter_db_fields
from .tools.copilot.utils.call_llm_test import call_llm_stream
from .tools.copilot.utils.parse_output import parse_generated_python_code

from .tools.get_function_info import get_function_info

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
                "import matplotlib.pyplot as plt", "import seaborn as sns"]

# print(get_db_info_prompt(engine, simple=True, example=False))


def get_db():
    return get_db_info_prompt(engine, example=True, simple=True)


def get_cot_code_prompt(question, tables=None, use_all_functions=False, selected_fields=None):
    rag_ans = ""
    knowledge = ""
    rag_ans = get_base_knowledge()
    knowledge = "\nBase knowledge: \n" + rag_ans + "\n"
    # print(rag_ans)

    function_set, function_info, function_import = get_function_info(question, llm, use_all_functions)
    # print(function_info)
    if function_info == "solved":
        return "solved", rag_ans, []
    # print(function_info)

    database = ""
    if query_database in function_set or exe_sql in function_set:
        if selected_fields is None:
            selected_fields = filter_db_fields(question, engine, llm, tables)
        if selected_fields and selected_fields.get("__no_db__"):
            database = ""
            selected_fields = None
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
        1. BEFORE creating any chart, check the number of unique categories in the data that will appear on x-axis or y-axis
        2. If categories > 10, you MUST:
           a) First yield a message: "Due to too many categories (N found), only the first/top 10 items are displayed. Please modify your question if you want to see specific items, e.g., 'show only the top 5' or 'show only categories A, B, C'."
           b) Then ACTUALLY filter the data to keep only top 10 (by count/frequency) or first 10
           c) Only AFTER filtering, create the plot
        3. If labels are still long after filtering, rotate them: plt.xticks(rotation=45) or plt.xticks(rotation=90)
        4. For long category names, consider horizontal bar chart (kind='barh') instead of vertical
        5. NEVER rotate labels without first filtering the data - rotation alone does not solve overcrowding!

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

    cot_prompt = "question:" + question + knowledge + database + pre_prompt + \
                 function_prompt + str(function_info) + \
                 module_prompt + example_code + remind_prompt
    return cot_prompt, rag_ans, function_import


def cot_agent(question, tables=None, use_all_functions=False, retries=2, print_rows=5, selected_fields=None):
    exp = None
    code = None
    for i in range(retries):
        cot_prompt, rag_ans, function_import = get_cot_code_prompt(question, tables, use_all_functions, selected_fields)
        print(rag_ans)
        # print(cot_prompt)
        if cot_prompt == "solved":
            return rag_ans, ""
        else:
            err_msg = ""
            for j in range(retries):
                code = get_py_code(cot_prompt + err_msg, llm)
                # print(code)
                # code = insert_yield_statements(code)
                code = insert_lines_into_function(code, function_import)
                code = insert_lines_into_function(code, IMPORTANT_MODULE)
                code = insert_lines_into_function(code, THIRD_MODULE)
                print(code)
                if code is None:
                    continue
                try:
                    result = execute_py_code(code)
                    cot_ans = ""
                    for item in result:
                        # print(item)
                        if isinstance(item, pd.DataFrame):
                            if item.index.size > 10:
                                cot_ans += df_to_markdown(item.head(print_rows)) + \
                                           "\nfirst {} rows of {}".format(print_rows, len(item)) + \
                                           "\nthe data above are just slice example, download csv to get full data\n"
                            else:
                                cot_ans += df_to_markdown(item)
                            html_link = pd_to_walker(item)
                            csv_link = pd_to_csv(item)
                            # cot_ans += wrap_html_url_with_markdown_link(html_link)
                            cot_ans += wrap_html_url_with_html_a(html_link)
                            cot_ans += wrap_csv_url_with_html_a(csv_link)
                        elif isinstance(item, str) and is_png_url(item):
                            cot_ans += "\n" + wrap_png_url_with_markdown_image(item) + "\n"
                        elif isinstance(item, str) and is_local_png_path(item):
                            cot_ans += "\n" + wrap_png_url_with_markdown_image(STATIC_URL + item[2:]) + "\n"
                        elif is_iframe_tag(str(item)):
                            cot_ans += "\n" + str(item) + "\n"
                        else:
                            cot_ans += "\n" + str(item) + "\n"
                        print(item)

                    ans = ""
                    # if rag_ans and rag_ans != "":
                    #     ans += "### Base knowledge: \n" + rag_ans + "\n\n"
                    ans += "### Result: \n" + cot_ans + "\n"
                    # print(ans)
                    # review_ans = get_ans_review(question, ans, code)
                    # ans += "## Summarize and review: \n" + review_ans + "\n"

                    logging.info(f"Question: {question}\nAnswer: {ans}\nCode: {code}\n")

                    return ans, code
                except Exception as e:
                    err_msg = "\n" + str(e) + "\n```python\n" + code + "\n```\n"
                    exp = str(e)
                    print(e)
                    continue
    return exp, code


def exe_cot_code(code, retries=2, print_rows=5):
    for j in range(retries):
        if code is None:
            continue
        cot_ans = ""
        try:
            result = execute_py_code(code)
            for item in result:
                if item is None:
                    item = " "
                print(item)
                if isinstance(item, pd.DataFrame):
                    if item.index.size > 10:
                        cot_ans += df_to_markdown(item.head(print_rows)) + \
                                   "\nfirst {} rows of {}".format(print_rows, len(item)) + \
                                   "\nthe data above are just slice example, download csv to get full data\n"
                    else:
                        cot_ans += df_to_markdown(item)
                    html_link = pd_to_walker(item)
                    csv_link = pd_to_csv(item)
                    # cot_ans += wrap_html_url_with_markdown_link(html_link)
                    cot_ans += wrap_html_url_with_html_a(html_link)
                    cot_ans += wrap_csv_url_with_html_a(csv_link)
                elif isinstance(item, str) and is_png_url(item):
                    cot_ans += "\n" + wrap_png_url_with_markdown_image(item) + "\n"
                elif isinstance(item, str) and is_iframe_tag(item):
                    html_map = str(item)
                    cot_ans += "\n" + html_map + "\n"
                else:
                    cot_ans += "\n" + str(item) + "\n"

        except Exception as e:
            print("Error:", e)
            if j < retries:
                continue
        # ans = "### Base knowledge: \n" + rag_ans + "\n\n"
        ans = "### Result: \n" + cot_ans + "\n"
        # print(ans)
        return ans
    return None


def get_cot_code(question, retries=2):
    cot_prompt, rag_ans, function_import = get_cot_code_prompt(question)
    print(rag_ans)
    # print(cot_prompt)
    if cot_prompt == "solved":
        return rag_ans, None
    else:
        err_msg = ""
        for j in range(retries):
            code = get_py_code(cot_prompt + err_msg, llm)
            # print(code)
            # code = insert_yield_statements(code)
            code = insert_lines_into_function(code, function_import)
            code = insert_lines_into_function(code, IMPORTANT_MODULE)
            code = insert_lines_into_function(code, THIRD_MODULE)
            print(code)
            if code is None:
                continue
            return code


def format_yield_item(item, print_rows=5):
    if isinstance(item, pd.DataFrame):
        if item.index.size > 10:
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


def generate_code_stream(question, tables=None, use_all_functions=False, retries=2, selected_fields=None):
    yield {"type": "status", "content": "正在分析问题..."}

    cot_prompt, rag_ans, function_import = get_cot_code_prompt(question, tables, use_all_functions, selected_fields)

    if cot_prompt == "solved":
        yield {"type": "solved", "content": rag_ans}
        yield {"type": "done", "content": ""}
        return

    yield {"type": "status", "content": "正在生成代码..."}

    full_prompt = cot_prompt
    err_msg = ""
    for j in range(retries):
        current_prompt = full_prompt + err_msg
        raw_content = ""
        for chunk in call_llm_stream(current_prompt, llm):
            raw_content += chunk
            yield {"type": "code_chunk", "content": chunk}

        code = parse_generated_python_code(raw_content)
        if code is None:
            yield {"type": "error", "content": "代码解析失败，正在重试..."}
            err_msg = "\n代码解析失败，请确保代码在 ```python 代码块中。\n"
            continue

        code = insert_lines_into_function(code, function_import)
        code = insert_lines_into_function(code, IMPORTANT_MODULE)
        code = insert_lines_into_function(code, THIRD_MODULE)
        print("\n[Generated Code]:\n", code)

        yield {"type": "code_complete", "content": code}
        yield {"type": "done", "content": ""}
        return

    yield {"type": "error", "content": "代码生成失败"}
    yield {"type": "done", "content": ""}


def execute_code_stream(code, retries=2, print_rows=5):
    yield {"type": "status", "content": "正在执行代码..."}

    err_msg = ""
    for j in range(retries):
        current_code = code
        try:
            result = execute_py_code(current_code)
            for item in result:
                formatted = format_yield_item(item, print_rows)
                yield {"type": "chunk", "content": formatted}
                print(item)

            yield {"type": "done", "content": ""}
            logging.info(f"Code executed successfully.\nCode: {code}\n")
            return
        except Exception as e:
            err_msg = str(e)
            print(f"Execution error: {e}")
            yield {"type": "status", "content": f"执行出错: {str(e)[:150]}..."}
            if j < retries - 1:
                yield {"type": "status", "content": "正在重试..."}
            continue

    yield {"type": "error", "content": f"执行失败: {err_msg[:200]}"}
    yield {"type": "done", "content": ""}
