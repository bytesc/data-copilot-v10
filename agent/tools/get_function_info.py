from .copilot.utils.call_llm_test import call_llm
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

IMPORTANT_FUNC = ["load_data"]

# FUNCTION_INFO = {key: func.__doc__ for key, func in FUNCTION_DICT.items()}
# ASSIST_FUNCTION_INFO = {key: ' '.join(func.__doc__ for func in funcs) for key, funcs in ASSIST_FUNCTION_DICT.items()}

FUNCTION_DESCRIPTION = {
    key: '\n'.join(func.__doc__.splitlines()[1:4]) for key, func in FUNCTION_DICT.items()
}


def get_function_prompt(question):
    # print(predict_grade_for_stu.__doc__)
    # print('\n'.join(predict_grade_for_stu.__doc__.splitlines()[1:3]))
    pre_prompt = """ 
Please select the functions need to use based on the question.
You can select multiple functions, to solve the problem.
You can choose as many as possible to ensure that the problem can be solved.
"""
    function_prompt = """ 
Here is the functions you can use:
"""
    example_code = """
Please only return the names list of the functions split by ","
Do not add any explanations of commands!!!

Example 1:
draw_graph, query_database
"""
    return "question:" + question + pre_prompt + function_prompt + str(FUNCTION_DESCRIPTION) + example_code


def get_function_info(question, llm, use_all_functions=False):
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
    for f in IMPORTANT_FUNC:
        if f not in function_list:
            function_list.append(f)
    function_set = set()
    for function_name in function_list:
        # print(function_name)
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
        function_info += "\n" + str(function.__doc__) + "\n"
        import_list = FUNCTION_IMPORT.get(function)
        if import_list:
            function_import.append(import_list)
    return function_set, function_info, function_import
