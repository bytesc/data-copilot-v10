from .parse_output import assert_skip

from agent.tools.tools_def import * #保留这一行，没错


def execute_py_code(code, assert_func=assert_skip):
    """
    执行生成的代码并返回结果。

    :param code: 生成的Python代码
    :param assert_func: 断言函数，用于验证结果
    :return: 执行结果，如果执行成功且通过断言则返回结果，否则返回None

    注意：``func`` 是生成器，函数体在调用方迭代 ``result`` 时才真正执行，
    因此执行耗时的统计放在调用方（``agent/agent.py`` 包住迭代的 ``finally``），
    这里不再重复记录 ``code_exec_time``，否则会与调用方重复累加。
    """
    try:
        local_namespace = {'result': None}
        exec(code, globals(), local_namespace)
        result = local_namespace['func']()
        assert_result = assert_func(result)
        if assert_result:
            raise Exception(assert_result)
        return result
    except Exception as e:
        print(f"An error occurred while executing the code: {type(e).__name__}: {str(e)}")
        raise e
