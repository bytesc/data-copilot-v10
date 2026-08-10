import json
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.agent import generate_and_execute_stream
from agent.tools.tools_def import engine, llm
from agent.tools.copilot.utils.call_llm_test import call_llm_stream, call_llm
from agent.tools.copilot.sql_code import parse_selected_fields_json
from agent.tools.search_db import get_db_overview_markdown, search_db_markdown, get_db_summary_for_agent
from agent.tools.search_func import get_func_catalog_markdown, search_func_by_keyword, get_func_summary_for_agent, get_func_docs_for
from agent.tools.get_function_info import FUNCTION_DICT, FUNCTION_DESCRIPTION
from data_access.session_log import record_session_operation
from data_access.observe_log import log_observe_cycle

router = APIRouter()


class ActInput(BaseModel):
    question: str
    action: str
    tables: Optional[List[str]] = None
    session_id: Optional[str] = None
    selected_fields: Optional[Dict[str, Any]] = None
    selected_functions: Optional[List[str]] = None
    conversation_history: Optional[List[str]] = None
    user_response: Optional[str] = None
    user_choice: Optional[str] = None
    search_keyword: Optional[str] = None


def _build_context(question: str, conversation_history: Optional[List[str]]):
    if conversation_history:
        context = "\n".join(conversation_history)
        return f"Context:\n{context}\n\nCurrent Question:\n{question}"
    return question


def _event_stream_act(
    question: str,
    action: str,
    tables: Optional[List[str]],
    session_id: str,
    selected_fields: Optional[Dict[str, Any]],
    selected_functions: Optional[List[str]],
    conversation_history: Optional[List[str]],
    request_url: str,
    user_response: Optional[str] = None,
    user_choice: Optional[str] = None,
    search_keyword: Optional[str] = None,
):
    """Act phase: execute exactly ONE action."""
    full_question = _build_context(question, conversation_history)

    if action == "search_db":
        yield from _act_search_db(full_question, session_id, tables, search_keyword)

    elif action == "search_func":
        yield from _act_search_func(full_question, session_id, search_keyword)

    elif action == "generate_and_execute":
        yield from _act_generate_and_execute(full_question, session_id, request_url, tables, selected_fields, selected_functions)

    elif action == "output_text":
        yield from _act_output_text(full_question, session_id, request_url)

    elif action == "ask_question":
        yield from _act_ask_question(full_question, session_id, request_url)

    elif action == "ask_choice":
        yield from _act_ask_choice(full_question, session_id, request_url)

    elif action == "summary_and_pause":
        yield from _act_summary_and_pause(full_question, session_id, request_url)

    elif action == "attempt_completion":
        yield from _act_attempt_completion(full_question, session_id, request_url)

    else:
        yield f"data: {json.dumps({'phase': 'act', 'type': 'error', 'content': f'Unknown action: {action}'}, ensure_ascii=False)}\n\n"


def _act_search_db(full_question: str, session_id: str, tables, search_keyword: Optional[str] = None):
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'search_db', 'type': 'status', 'content': '正在搜索数据库信息...'}, ensure_ascii=False)}\n\n"

    if search_keyword and search_keyword.strip():
        full_schema = search_db_markdown(engine, search_keyword.strip(), tables)
    else:
        full_schema = get_db_overview_markdown(engine, tables, include_samples=True)

    prompt = f"""Analyze the following database schema and the user's question to select the relevant tables and columns.

{full_schema}

Question:
{full_question}

Output ONLY a JSON object mapping table names to their needed columns. Use an empty list [] for a table to select all its columns. Use an empty object {{}} to select all tables and all columns. Use {{"__no_db__": true}} if no database query is needed.

Example:
```json
{{"users": ["id", "name", "email"], "orders": []}}
```
"""
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'search_db', 'type': 'status', 'content': '正在分析所需字段...'}, ensure_ascii=False)}\n\n"

    response = call_llm(prompt, llm)
    selected_fields = parse_selected_fields_json(response.content) or {}

    if selected_fields and not selected_fields.get("__no_db__"):
        display_content = get_db_overview_markdown(engine, tables, include_samples=True, selected_fields=selected_fields)
    else:
        display_content = full_schema

    log_observe_cycle(session_id, 0, "act", "search_db",
                      prompt=prompt[:5000], response=response.content[:5000],
                      token_estimate=len(prompt) // 3)

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'search_db', 'type': 'done', 'content': display_content, 'db_context': full_schema, 'selected_fields': selected_fields, 'search_keyword': search_keyword}, ensure_ascii=False)}\n\n"


def _act_search_func(full_question: str, session_id: str, search_keyword: Optional[str] = None):
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'search_func', 'type': 'status', 'content': '正在搜索函数信息...'}, ensure_ascii=False)}\n\n"

    if search_keyword and search_keyword.strip():
        full_catalog = search_func_by_keyword(search_keyword.strip())
    else:
        full_catalog = get_func_catalog_markdown()

    func_names = ", ".join(FUNCTION_DICT.keys())
    prompt = f"""Analyze the following function catalog and the user's question to select the needed functions.

{full_catalog}

Question:
{full_question}

Available functions: {func_names}

Output ONLY the function names separated by commas. Return "solved" if no functions are needed.

Example:
exe_sql, get_save_image_path
"""
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'search_func', 'type': 'status', 'content': '正在分析所需函数...'}, ensure_ascii=False)}\n\n"

    response = call_llm(prompt, llm)
    raw = response.content.strip()
    if raw == "solved":
        selected_functions = []
    else:
        selected_functions = [f.strip() for f in raw.split(',') if f.strip() in FUNCTION_DICT]

    if selected_functions:
        display_content = get_func_docs_for(selected_functions)
    else:
        display_content = "*(No functions selected)*"

    log_observe_cycle(session_id, 0, "act", "search_func",
                      prompt=prompt[:5000], response=response.content[:5000],
                      token_estimate=len(prompt) // 3)

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'search_func', 'type': 'done', 'content': display_content, 'func_context': full_catalog, 'selected_functions': selected_functions, 'search_keyword': search_keyword}, ensure_ascii=False)}\n\n"


def _act_generate_and_execute(full_question: str, session_id: str, request_url: str, tables, selected_fields, selected_functions):
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'generate', 'type': 'status', 'content': '正在生成并执行代码...'}, ensure_ascii=False)}\n\n"
    full_code = ""
    full_ans = ""
    exec_error = None
    prompt_length = 0
    for event in generate_and_execute_stream(
        full_question, tables, True,
        selected_fields=selected_fields,
        selected_functions=selected_functions,
    ):
        if event.get("type") == "code_complete" and event.get("phase") == "code":
            full_code = event.get("content", "")
        if event.get("type") == "done" and event.get("phase") == "exec":
            prompt_length = event.get("prompt_length", 0)
        if event.get("type") == "chunk" and event.get("phase") == "exec":
            full_ans += event.get("content", "")
        if event.get("type") == "error" and event.get("phase") == "exec":
            exec_error = event.get("content", "")
        yield f"data: {json.dumps({**event, 'phase': 'act', 'sub_phase': event.get('phase', 'exec')}, ensure_ascii=False)}\n\n"
    if exec_error:
        record_session_operation(session_id, request_url, full_question, ans=full_ans, code=full_code, result_type="error", msg=exec_error[:500], prompt_length=prompt_length)
    else:
        record_session_operation(session_id, request_url, full_question, ans=full_ans, code=full_code, result_type="success", prompt_length=prompt_length)


def _act_output_text(full_question: str, session_id: str, request_url: str):
    prompt = f"""Based on the context and current state, provide a clear and informative response. Include relevant data, analysis, or explanations. Do NOT generate code. Use markdown formatting.

{full_question}"""

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'output_text', 'type': 'status', 'content': '正在生成回复...'}, ensure_ascii=False)}\n\n"
    text_content = ""
    for chunk in call_llm_stream(prompt, llm):
        text_content += chunk
        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'output_text', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'output_text', 'type': 'done', 'content': text_content}, ensure_ascii=False)}\n\n"

    record_session_operation(session_id, request_url, full_question, ans=text_content, result_type="success", prompt_length=len(prompt))


def _act_ask_question(full_question: str, session_id: str, request_url: str):
    prompt = f"""Based on the context, you need to ask the user a clarifying question to proceed. Output ONLY the question text, nothing else.

{full_question}"""

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'ask_question', 'type': 'status', 'content': '需要用户确认...'}, ensure_ascii=False)}\n\n"
    question_text = ""
    for chunk in call_llm_stream(prompt, llm):
        question_text += chunk
        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'ask_question', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'ask_question', 'type': 'done', 'content': question_text, 'needs_user_input': True}, ensure_ascii=False)}\n\n"

    record_session_operation(session_id, request_url, full_question, ans=question_text, result_type="success", prompt_length=len(prompt))


def _act_ask_choice(full_question: str, session_id: str, request_url: str):
    prompt = f"""Based on the context, you need to present the user with choices. Output ONLY a JSON object with fields "question" (string) and "choices" (array of 2-5 strings). No other text.

Example: {{"question": "Which table should I use?", "choices": ["table_a", "table_b", "table_c"]}}

{full_question}"""

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'ask_choice', 'type': 'status', 'content': '需要用户选择...'}, ensure_ascii=False)}\n\n"
    raw = ""
    for chunk in call_llm_stream(prompt, llm):
        raw += chunk
        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'ask_choice', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

    try:
        parsed = json.loads(raw)
        question_text = parsed.get("question", "")
        choices = parsed.get("choices", [])
    except json.JSONDecodeError:
        question_text = raw.strip()
        choices = []

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'ask_choice', 'type': 'done', 'content': question_text, 'choices': choices, 'needs_user_input': True}, ensure_ascii=False)}\n\n"

    record_session_operation(session_id, request_url, full_question, ans=raw, result_type="success", prompt_length=len(prompt))


def _act_summary_and_pause(full_question: str, session_id: str, request_url: str):
    prompt = f"""Summarize the current progress: what has been accomplished, what data was found, and what remains to be done. Be concise and clear. Do NOT generate code. Use markdown.

{full_question}"""

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'summary', 'type': 'status', 'content': '正在总结进度...'}, ensure_ascii=False)}\n\n"
    summary = ""
    for chunk in call_llm_stream(prompt, llm):
        summary += chunk
        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'summary', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'summary', 'type': 'done', 'content': summary, 'paused': True}, ensure_ascii=False)}\n\n"

    record_session_operation(session_id, request_url, full_question, ans=summary, result_type="success", prompt_length=len(prompt))


def _act_attempt_completion(full_question: str, session_id: str, request_url: str):
    prompt = f"""The task is complete. Present the final results, key findings, and conclusions. Use markdown formatting for clarity. Be thorough but concise.

{full_question}"""

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'completion', 'type': 'status', 'content': '正在生成最终结果...'}, ensure_ascii=False)}\n\n"
    final = ""
    for chunk in call_llm_stream(prompt, llm):
        final += chunk
        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'completion', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'completion', 'type': 'done', 'content': final, 'completed': True}, ensure_ascii=False)}\n\n"

    record_session_operation(session_id, request_url, full_question, ans=final, result_type="success", prompt_length=len(prompt))


@router.post("/api/act/stream/")
async def act_stream_api(request: Request, user_input: ActInput):
    return StreamingResponse(
        _event_stream_act(
            user_input.question,
            user_input.action,
            user_input.tables,
            user_input.session_id or "",
            user_input.selected_fields,
            user_input.selected_functions,
            user_input.conversation_history,
            request.url.path,
            user_input.user_response,
            user_input.user_choice,
            user_input.search_keyword,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )