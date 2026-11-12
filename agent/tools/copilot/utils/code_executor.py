from .parse_output import assert_skip
from .sandbox import execute_in_sandbox


def execute_py_code(code, assert_func=assert_skip):
    """
    执行生成的代码并返回结果。

    :param code: 生成的Python代码
    :param assert_func: 断言函数，用于验证结果
    :return: 执行结果，如果执行成功且通过断言则返回结果，否则返回None

    代码审查通过后不再在本进程内执行：改为委托给一次性沙箱子进程
    （``agent/tools/copilot/utils/sandbox/``），返回一个可迭代的结果生成器。
    这里刻意不保留任何主进程 ``exec`` 的 fallback 路径。

    注意：``func`` 在沙箱子进程内才是生成器，函数体在执行结果的迭代过程中真正
    运行；因此执行耗时的统计仍放在调用方（``agent/agent.py`` 包住迭代的
    ``finally``），这里不再重复记录 ``code_exec_time``。
    """
    result = execute_in_sandbox(code)
    assert_result = assert_func(result)
    if assert_result:
        raise Exception(assert_result)
    return result
