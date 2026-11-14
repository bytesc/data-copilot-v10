from .parse_output import assert_skip
from .sandbox import execute_in_sandbox

# Kept for the in-process fallback path (``_execute_in_process``): the star import
# puts the whitelisted tool functions and their pre-imported libraries (pd / np /
# plt / ...) into THIS module's globals, which ``exec(code, globals(), ...)`` below
# relies on. Do not remove.
from agent.tools.tools_def import *  # noqa: F401,F403,E402

# Imported AFTER the star import: ``tools_def`` also re-exports a ``config_data``
# (the same object), so this keeps the toggle's source explicit and unshadowed.
from config.get_config import config_data  # noqa: E402


def execute_py_code(code, assert_func=assert_skip, session_id=""):
    """
    执行生成的代码并返回结果。

    :param code: 生成的Python代码
    :param assert_func: 断言函数，用于验证结果
    :param session_id: 当前请求的 session id，写入沙箱审计日志
    :return: 执行结果，如果执行成功且通过断言则返回结果，否则返回None

    由主配置 `enable_code_sandbox` 决定执行方式：
    * true（默认）：委托给一次性沙箱子进程
      （``agent/tools/copilot/utils/sandbox/``），返回可迭代的结果生成器；
    * false：在主进程内 ``exec``（旧行为：无隔离、无资源限制、无文件/网络管控）。

    注意：``func`` 是生成器，函数体在调用方迭代 ``result`` 时才真正执行，
    因此执行耗时的统计仍放在调用方（``agent/agent.py`` 包住迭代的 ``finally``），
    这里不再重复记录 ``code_exec_time``。
    """
    if config_data.get("enable_code_sandbox", True):
        result = execute_in_sandbox(code, session_id=session_id)
    else:
        result = _execute_in_process(code)
    assert_result = assert_func(result)
    if assert_result:
        raise Exception(assert_result)
    return result


def _execute_in_process(code):
    """Legacy in-process execution (no isolation).

    Only used when ``enable_code_sandbox`` is false. Mirrors the pre-sandbox
    implementation: run the generated code in the main process with this module's
    globals (which carry the whitelisted tools/libraries via the star import), and
    return the ``func()`` generator directly.
    """
    try:
        local_namespace = {"result": None}
        exec(code, globals(), local_namespace)
        return local_namespace["func"]()
    except Exception as e:
        print(f"An error occurred while executing the code: {type(e).__name__}: {str(e)}")
        raise
