from .copilot.utils.call_llm_test import call_llm, call_llm_stream
from .tools_def import draw_graph, query_database, explain_data, exe_sql, draw_compare_graph, load_data, \
    get_save_image_path, search_web, fetch_webpage

FUNCTION_DICT = {
    # "query_database": query_database,
    # "draw_graph": draw_graph,
    # "draw_compare_graph": draw_compare_graph,
    # "explain_data": explain_data,
    "exe_sql": exe_sql,
    "load_data": load_data,
    "get_save_image_path": get_save_image_path,
    "search_web": search_web,
    "fetch_webpage": fetch_webpage,
}

FUNCTION_IMPORT = {
    query_database: "from agent.tools.tools_def import query_database",
    explain_data: "from agent.tools.tools_def import explain_data",
    draw_graph: "from agent.tools.tools_def import draw_graph",
    draw_compare_graph: "from agent.tools.tools_def import draw_compare_graph",
    exe_sql: "from agent.tools.tools_def import exe_sql",
    load_data: "from agent.tools.tools_def import load_data",
    get_save_image_path: "from agent.tools.tools_def import get_save_image_path",
    search_web: "from agent.tools.tools_def import search_web",
    fetch_webpage: "from agent.tools.tools_def import fetch_webpage",
}

ASSIST_FUNCTION_DICT = {
    # query_database: [explain_data],
    # exe_sql: [explain_data],
}

IMPORTANT_FUNC = ["load_data", "get_save_image_path"]

# FUNCTION_INFO = {key: func.__doc__ for key, func in FUNCTION_DICT.items()}
# ASSIST_FUNCTION_INFO = {key: ' '.join(func.__doc__ for func in funcs) for key, funcs in ASSIST_FUNCTION_DICT.items()}

FUNCTION_DESCRIPTION = {
    key: '\n'.join(func.__doc__.splitlines()[1:4]) for key, func in FUNCTION_DICT.items()
}


def get_function_prompt(question):
    pre_prompt = """ 
Please select ALL functions that will be called in the generated code to solve the problem.
Include every function from the list below that will appear in the code, including utility functions.
"""
    function_prompt = """ 
Here is the functions you can use:
"""
    example_code = """
Please only return the names list of the functions split by ","
Do not add any explanations of commands!!!
Return an empty response if you think all functions are needed.
Return "solved" if no functions are needed.

Example 1:
exe_sql, get_save_image_path
"""
    return "question:" + question + pre_prompt + function_prompt + str(FUNCTION_DESCRIPTION) + example_code


def get_function_info(question, llm, use_all_functions=False, brief=False):
    if use_all_functions:
        function_set = set(FUNCTION_DICT.values())
        for main_function in FUNCTION_DICT.values():
            assist_functions = ASSIST_FUNCTION_DICT.get(main_function)
            if assist_functions:
                for assist_function in assist_functions:
                    function_set.add(assist_function)
        function_info = ""
        function_import = []
        for function in function_set:
            if brief:
                function_info += "\n" + '\n'.join(str(function.__doc__).splitlines()[:3]) + "\n"
            else:
                function_info += "\n" + str(function.__doc__) + "\n"
            import_list = FUNCTION_IMPORT.get(function)
            if import_list:
                function_import.append(import_list)

        return function_set, function_info, function_import

    function_prompt = get_function_prompt(question)
    function_list_str = call_llm(function_prompt, llm).content
    if function_list_str == "solved":
        return {}, "solved", []
    function_list = [part.strip() for part in function_list_str.split(',')]
    function_list = [f for f in function_list if f]
    if not function_list:
        return get_function_info(question, llm, use_all_functions=True, brief=brief)
    for f in IMPORTANT_FUNC:
        if f not in function_list:
            function_list.append(f)
    function_set = set()
    for function_name in function_list:
        function = FUNCTION_DICT.get(function_name)
        if function:
            function_set.add(function)
            assist_functions = ASSIST_FUNCTION_DICT.get(function)
            if assist_functions:
                for assist_function in assist_functions:
                    function_set.add(assist_function)
    function_info = ""
    function_import = []
    for function in function_set:
        if brief:
            function_info += "\n" + '\n'.join(str(function.__doc__).splitlines()[:3]) + "\n"
        else:
            function_info += "\n" + str(function.__doc__) + "\n"
        import_list = FUNCTION_IMPORT.get(function)
        if import_list:
            function_import.append(import_list)
    return function_set, function_info, function_import


def filter_functions_stream(question, llm):
    yield {"type": "status", "content": "正在分析可用函数..."}

    function_prompt = get_function_prompt(question)
    full_content = ""

    for chunk in call_llm_stream(function_prompt, llm):
        full_content += chunk
        yield {"type": "chunk", "content": chunk}

    function_list_str = full_content.strip()
    if function_list_str == "solved":
        yield {"type": "done", "content": full_content, "selected_functions": [], "solved": True}
        return

    function_list = [part.strip() for part in function_list_str.split(',')]
    function_list = [f for f in function_list if f]
    if not function_list:
        selected_functions = list(FUNCTION_DICT.keys())
    else:
        selected_functions = function_list
        for f in IMPORTANT_FUNC:
            if f not in selected_functions:
                selected_functions.append(f)

    yield {"type": "done", "content": full_content, "selected_functions": selected_functions, "solved": False}
