import logging

from .tools.tools_def import engine, llm

from .tools.copilot.sql_code import get_db_info_prompt

from .tools.get_function_info import FUNCTION_DESCRIPTION

from .tools.copilot.utils.call_llm_test import call_llm, call_llm_stream


def get_plain_chat_prompt(question, tables=None, selected_fields=None):
    function_info = "\n".join(FUNCTION_DESCRIPTION.values())

    function_prompt = """
You can use the following functions:
"""
    data_prompt = get_db_info_prompt(engine, simple=True, example=False, tables=tables, selected_fields=selected_fields)
    database = "\nThe database content: \n" + data_prompt + "\n"

    pre_prompt = """
You are a helpful assistant. Answer the user's question based on the database and available functions provided.
"""
    prompt = "question:" + question + database + pre_prompt + function_prompt + function_info
    return prompt


def get_plain_chat(question: str, tables=None, selected_fields=None):
    prompt = get_plain_chat_prompt(question, tables, selected_fields)
    ans = call_llm(prompt, llm)
    return ans.content


def get_plain_chat_stream(question: str, tables=None, selected_fields=None):
    prompt = get_plain_chat_prompt(question, tables, selected_fields)
    for chunk in call_llm_stream(prompt, llm):
        yield chunk