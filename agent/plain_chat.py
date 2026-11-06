import logging

from .tools.tools_def import engine, llm

from .tools.copilot.sql_code import get_db_info_prompt

from .tools.get_function_info import FUNCTION_DESCRIPTION

from utils.context_trim import call_with_context_retry, stream_with_context_retry, cap_text


def get_plain_chat_prompt(question, tables=None, selected_fields=None, level=0):
    function_info = "\n".join(FUNCTION_DESCRIPTION.values())

    function_prompt = """
You can use the following functions:
"""
    data_prompt = get_db_info_prompt(engine, simple=True, example=False, tables=tables, selected_fields=selected_fields)
    database = "\nThe database content: \n" + cap_text(data_prompt, level) + "\n"

    pre_prompt = """
You are a helpful assistant. Answer the user's question based on the database and available functions provided.
"""
    prompt = pre_prompt + function_prompt + cap_text(function_info, level) + database + "question:" + cap_text(question, level)
    return prompt


def get_plain_chat(question: str, tables=None, selected_fields=None):
    ans = call_with_context_retry(lambda lvl: get_plain_chat_prompt(question, tables, selected_fields, level=lvl), llm)
    return ans.content


def get_plain_chat_stream(question: str, tables=None, selected_fields=None):
    prompt = get_plain_chat_prompt(question, tables, selected_fields)
    yield {"prompt_length": len(prompt)}
    for chunk, _ in stream_with_context_retry(lambda lvl: get_plain_chat_prompt(question, tables, selected_fields, level=lvl), llm):
        yield chunk