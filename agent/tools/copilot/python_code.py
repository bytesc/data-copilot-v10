from .utils import call_llm_test
from .utils.code_insert import insert_lines_into_function

from .utils.parse_output import parse_generated_python_code

from .utils.code_executor import execute_py_code_with_data
from .utils.parse_output import assert_png_file
from .examples.ask_ai_for_graph import get_ask_graph_prompt, get_ask_compare_graph_prompt

import logging
import pandas as pd

IMPORTANT_MODULE = ["import math"]
THIRD_MODULE = ["import pandas as pd", "import numpy as np"]


pd.set_option('display.max_columns', None)


def get_py_code_with_data_dict(question, data_dict, llm, retries=3):
    def slice_dfs(df_dict, lines=3):
        top_five_dict = {}
        for key, df in df_dict.items():
            top_five_dict[key] = df.head(min(lines, len(df)))
        return top_five_dict

    data_slice = slice_dfs(data_dict)
    pre_prompt = """
Define a Python function called `func` 
that takes only a single dictionary called `data_dict` as input parameter.
The dictionary has string keys and pandas DataFrame values.
The function should perform the following operations:
"""

    data_prompt = """
Here is the data_dict sample (it just shows data structure samples, not real data): 
""" + str(data_slice)

    end_prompt = """
Remind:
1. All code should be completed in a single markdown code block without any comments, explanations or cmds.
2. The function should not be called, do not print anything in the function.
3. Please import the module you need, modules must be imported inside the function.
4. Do not mock any data !!!
5. Do not use `input()` !!!
6. Access DataFrames from data_dict using keys, e.g., data_dict['key_name']
"""

    final_prompt = pre_prompt + "\n" + data_prompt + end_prompt + question

    retries_times = 0
    error_msg = ""
    while retries_times <= retries:
        retries_times += 1
        ans = call_llm_test.call_llm(final_prompt + error_msg, llm)
        ans_code = parse_generated_python_code(ans.content)
        if ans_code is not None:
            return ans_code
        else:
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
            logging.error(str(ans.content) + "No code was generated.")
            print("No code was generated.")
            continue

def get_py_code_with_data(question, data, llm, retries=3):
    def slice_dfs(df_dict, lines=3):
        top_five_dict = {}
        for key, df in df_dict.items():
            top_five_dict[key] = df.head(min(lines, len(df)))
        return top_five_dict

    data_slice = slice_dfs(data)
    pre_prompt = """
Define a Python function called `func` 
that takes only a single pandas dataframe called `data` as input parameter
that performs the following operations:
"""

    data_prompt = """
Here is the dataframe sample(it is just data structure samples not real data): 
""" + str(data_slice)

    end_prompt = """
Remind:
1. All code should be completed in a single markdown code block without any comments, explanations or cmds.
2. The function should not be called, do not print anything in the function.
3. Please import the module you need, modules must be imported inside the function.
4. Do not mock any data !!!
5. Do not use `input()` !!!
"""

    final_prompt = pre_prompt + "\n" + data_prompt + end_prompt + question

    retries_times = 0
    error_msg = ""
    while retries_times <= retries:
        retries_times += 1
        ans = call_llm_test.call_llm(final_prompt + error_msg, llm)
        ans_code = parse_generated_python_code(ans.content)
        if ans_code is not None:
            return ans_code
        else:
            error_msg = """
code should only be in a md code block: 
```python
def func(data):
    import pandas as pd
    import math
    # some python code
```
without any additional comments, explanations or cmds !!!
"""
            logging.error(str(ans.content) + "No code was generated.")
            print("No code was generated.")
            continue


def get_py_code(question, llm, retries=3):
    pre_prompt = """
Define a Python function called `func` 
that takes no input parameter
that performs the following operations:
"""

    end_prompt = """
Remind:
1. All code should be completed in a single markdown code block without any comments, explanations or cmds.
2. The function should not be called, do not print anything in the function.
3. Please import the module you need, modules must be imported inside the function.
4. Do not mock any data !!!
5. Do not use `input()` !!!
"""

    final_prompt = pre_prompt + "\n" + end_prompt + question

    retries_times = 0
    error_msg = ""
    while retries_times <= retries:
        retries_times += 1
        ans = call_llm_test.call_llm(final_prompt + error_msg, llm)
        ans_code = parse_generated_python_code(ans.content)
        if ans_code is not None:
            return ans_code
        else:
            error_msg = """
code should only be in a md code block: 
```python
def func():
    import math
    # some python code
```
without any additional comments, explanations or cmds !!!
"""
            logging.error(str(ans.content) + "No code was generated.")
            print("No code was generated.")
            continue


def draw_graph_func(question, data, llm, col_explanation=None, retries=2):
    exp = None
    for i in range(retries):
        question = get_ask_graph_prompt(question, col_explanation)
        err_msg = ""
        for j in range(retries):
            code = get_py_code_with_data(question + err_msg, data, llm)
            if code is None:
                continue
            try:
                code = insert_lines_into_function(code, IMPORTANT_MODULE)
                code = insert_lines_into_function(code, THIRD_MODULE)
                result = execute_py_code_with_data(code, data, assert_png_file)
                return result
            except Exception as e:
                err_msg = "\n" + str(e) + "\n```python\n" + code + "\n```\n"
                print(e)
                exp = e
                continue
    return None


def draw_compare_graph_func(question, data_dict, llm, col_explanation=None, retries=2):
    exp = None
    for i in range(retries):
        question = get_ask_compare_graph_prompt(question, col_explanation)
        err_msg = ""
        for j in range(retries):
            code = get_py_code_with_data_dict(question + err_msg, data_dict, llm)
            if code is None:
                continue
            try:
                code = insert_lines_into_function(code, IMPORTANT_MODULE)
                code = insert_lines_into_function(code, THIRD_MODULE)
                print(code)
                result = execute_py_code_with_data(code, data_dict, assert_png_file)
                return result
            except Exception as e:
                err_msg = "\n" + str(e) + "\n```python\n" + code + "\n```\n"
                print(e)
                exp = e
                continue
    return None
