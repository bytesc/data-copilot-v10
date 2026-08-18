import json
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.agent import generate_and_execute_stream
from agent.tools.base_knowledge.get_base_knowledge import DB_BRIEF, DB_QUERY_GUIDE, get_base_knowledge
from agent.tools.tools_def import engine, llm
from agent.tools.copilot.utils.call_llm_test import call_llm_stream, call_llm
from agent.tools.copilot.sql_code import parse_selected_fields_json
from agent.tools.search_db import get_db_overview_markdown, search_db_markdown, get_db_summary_for_agent
from agent.tools.search_func import get_func_catalog_markdown, search_func_by_keyword, get_func_summary_for_agent, get_func_docs_for
from agent.tools.get_function_info import FUNCTION_DICT
from data_access.session_log import record_session_operation
from data_access.observe_log import log_observe_cycle
from utils.front_utils import history_to_text
from utils.context_trim import prepare_trimmed_context, save_session_step

router = APIRouter()


class ActInput(BaseModel):
    question: str
    action: str
    session_id: Optional[str] = None
    conversation_history: Optional[List[dict]] = None
    params: Optional[Dict[str, Any]] = None


def _build_context(question: str, conversation_history: Optional[List[dict]], session_id: str = ""):
    trimmed = prepare_trimmed_context(session_id, conversation_history)
    if conversation_history:
        return history_to_text(trimmed)
    return question


def _build_act_entries(action: str, act_data: dict) -> List[dict]:
    entries = []
    if action == "explore_schema":
        entry = {"role": "assistant", "type": "act", "action": "explore_schema"}
        if act_data.get("selected_fields") is not None:
            entry["selected_fields"] = act_data["selected_fields"]
        if act_data.get("explore_plan"):
            entry["explore_plan"] = act_data["explore_plan"]
        if act_data.get("search_result"):
            entry["search_result"] = act_data["search_result"]
        entries.append(entry)
    elif action == "explore_functions":
        entry = {"role": "assistant", "type": "act", "action": "explore_functions"}
        if act_data.get("selected_functions") is not None:
            entry["selected_functions"] = act_data["selected_functions"]
        if act_data.get("search_result"):
            entry["search_result"] = act_data["search_result"]
        entries.append(entry)
    elif action == "generate_and_execute":
        full_code = act_data.get("full_code", "")
        full_ans = act_data.get("full_ans", "")
        exec_error = act_data.get("exec_error")
        if full_ans and not exec_error and full_code:
            entries.append({"role": "assistant", "type": "act", "action": "generate_and_execute", "code": full_code, "result": full_ans})
        elif exec_error:
            entry = {"role": "assistant", "type": "act", "action": "generate_and_execute", "error": exec_error}
            if full_code:
                entry["code"] = full_code
            if full_ans:
                entry["result"] = full_ans
            entries.append(entry)
    return entries


def _event_stream_act(
    question: str,
    action: str,
    session_id: str,
    conversation_history: Optional[List[dict]],
    params: Optional[Dict[str, Any]] = None,
    request_json: str = "",
):
    """Act phase: execute exactly ONE action."""
    full_question = _build_context(question, conversation_history, session_id)
    params = params or {}
    search_keyword = params.get("search_keyword")
    tables = params.get("tables")
    selected_fields = params.get("selected_fields")
    selected_functions = params.get("selected_functions")

    act_data = {}
    if action == "explore_schema":
        act_data = yield from _act_explore_schema(full_question, session_id, tables, search_keyword)

    elif action == "explore_functions":
        act_data = yield from _act_explore_functions(full_question, session_id, search_keyword)

    elif action == "generate_and_execute":
        act_data = yield from _act_generate_and_execute(full_question, session_id, tables, selected_fields, selected_functions, request_json)

    else:
        yield f"data: {json.dumps({'phase': 'act', 'type': 'error', 'content': f'Unknown action: {action}'}, ensure_ascii=False)}\n\n"

    new_entries = _build_act_entries(action, act_data)
    if new_entries:
        save_session_step(session_id, conversation_history, new_entries)


def _act_explore_schema(full_question: str, session_id: str, tables, search_keyword: Optional[str] = None):
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_schema', 'type': 'msg', 'content': '正在搜索数据库信息...'}, ensure_ascii=False)}\n\n"

    base_knowledge = get_base_knowledge()

    if search_keyword and search_keyword.strip():
        full_schema = search_db_markdown(engine, search_keyword.strip(), tables)
    else:
        full_schema = get_db_overview_markdown(engine, tables, include_samples=True)

    prompt = f"""Analyze the following database schema and the user's question to select the relevant tables and columns.

{base_knowledge}

{DB_BRIEF}

{DB_QUERY_GUIDE}

{full_schema}

Context:
{full_question}

Output ONLY a JSON object mapping table names to their needed columns. Use an empty list [] for a table to select all its columns. 
Use an empty object {{}} to select all tables and all columns. 
Use {{"__no_db__": true}} if no database query is needed or no relivent data in the database.
Include a "plan" field describing the query plan in text.

Example:
```json
{{"users": ["id", "name", "email"], "orders": [], "plan": "Query the users table to get customer IDs and emails, then join with orders table to find purchase records"}}
```
"""
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_schema', 'type': 'msg', 'content': '正在分析所需字段...'}, ensure_ascii=False)}\n\n"

    raw = ""
    for chunk in call_llm_stream(prompt, llm):
        raw += chunk
        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_schema', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
    selected_fields = parse_selected_fields_json(raw) or {}
    explore_plan = selected_fields.pop("plan", "") if isinstance(selected_fields, dict) else ""

    if selected_fields and not selected_fields.get("__no_db__"):
        display_content = get_db_overview_markdown(engine, tables, include_samples=True, selected_fields=selected_fields)
    elif selected_fields and selected_fields.get("__no_db__"):
        display_content = "*(No database tables needed)*"
    else:
        display_content = full_schema

    log_observe_cycle(session_id, 0, "act", "explore_schema",
                      prompt=prompt[:5000], response=raw[:5000],
                      exec_result=display_content[:10000],
                      token_estimate=len(prompt) // 3)

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_schema', 'type': 'done', 'content': display_content, 'result': {'selected_fields': selected_fields, 'db_context': full_schema, 'explore_plan': explore_plan}, 'search_keyword': search_keyword}, ensure_ascii=False)}\n\n"

    return {"selected_fields": selected_fields, "explore_plan": explore_plan, "search_result": display_content}


def _act_explore_functions(full_question: str, session_id: str, search_keyword: Optional[str] = None):
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_functions', 'type': 'msg', 'content': '正在搜索函数信息...'}, ensure_ascii=False)}\n\n"

    if search_keyword and search_keyword.strip():
        full_catalog = search_func_by_keyword(search_keyword.strip())
    else:
        full_catalog = get_func_catalog_markdown()

    func_names = ", ".join(FUNCTION_DICT.keys())
    prompt = f"""Analyze the following function catalog and the user's question to select the needed functions.

{full_catalog}

Context:
{full_question}

Available functions: {func_names}

Output ONLY the function names separated by commas. Return "solved" if no functions are needed.

Example:
exe_sql, get_save_image_path
"""
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_functions', 'type': 'status', 'content': '正在分析所需函数...'}, ensure_ascii=False)}\n\n"

    raw = ""
    for chunk in call_llm_stream(prompt, llm):
        raw += chunk
        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_functions', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
    raw_text = raw
    raw = raw.strip()
    if raw == "solved":
        selected_functions = []
    else:
        selected_functions = [f.strip() for f in raw.split(',') if f.strip() in FUNCTION_DICT]

    if selected_functions:
        display_content = get_func_docs_for(selected_functions)
    else:
        display_content = "*(No functions selected)*"

    log_observe_cycle(session_id, 0, "act", "explore_functions",
                      prompt=prompt[:5000], response=raw_text[:5000],
                      exec_result=display_content[:10000],
                      token_estimate=len(prompt) // 3)

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_functions', 'type': 'done', 'content': display_content, 'result': {'selected_functions': selected_functions, 'func_context': full_catalog}, 'search_keyword': search_keyword}, ensure_ascii=False)}\n\n"

    return {"selected_functions": selected_functions, "search_result": display_content}


def _act_generate_and_execute(full_question: str, session_id: str, tables, selected_fields, selected_functions, request_json: str = ""):
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'generate', 'type': 'status', 'content': '正在生成并执行代码...'}, ensure_ascii=False)}\n\n"
    full_code = ""
    full_ans = ""
    exec_error = None
    for event in generate_and_execute_stream(
        full_question, tables, retries=2,
        selected_fields=selected_fields,
        selected_functions=selected_functions,
    ):
        if event.get("sub_type") == "code_chunk":
            if exec_error:
                full_code = ""
                full_ans = ""
                exec_error = None
            full_code += event.get("content", "")
        if event.get("sub_type") == "code_complete":
            full_code = event.get("content", "")
        if event.get("sub_type") == "exec_chunk":
            full_ans += event.get("content", "")
        if event.get("sub_type") == "code_exe_error":
            exec_error = event.get("content", "")

        if event.get("type") == "done" and event.get("sub_phase") == "exec":
            full_code = event.get("code", full_code)
            full_ans = event.get("content", full_ans)
            event = {
                **event,
                "result": {
                    "code": full_code,
                    "exec_result": full_ans,
                    "error": exec_error,
                }
            }
        yield f"data: {json.dumps({**event}, ensure_ascii=False)}\n\n"
    if exec_error:
        record_session_operation(session_id, "/api/act/stream/", request_json, ans=full_ans, code=full_code, result_type="error", msg=exec_error[:500])
        log_observe_cycle(session_id, 0, "act", "generate_and_execute",
                          prompt=full_question[:10000], response=full_code[:10000],
                          exec_code=full_code[:10000], exec_result=full_ans[:10000],
                          exec_error=exec_error[:2000])
    else:
        record_session_operation(session_id, "/api/act/stream/", request_json, ans=full_ans, code=full_code, result_type="success")
        log_observe_cycle(session_id, 0, "act", "generate_and_execute",
                          prompt=full_question[:10000], response=full_code[:10000],
                          exec_code=full_code[:10000], exec_result=full_ans[:10000])

    return {"full_code": full_code, "full_ans": full_ans, "exec_error": exec_error}


@router.post("/api/act/stream/")
async def act_stream_api(request: Request, user_input: ActInput):
    return StreamingResponse(
        _event_stream_act(
            user_input.question,
            user_input.action,
            user_input.session_id or "",
            user_input.conversation_history,
            user_input.params,
            user_input.model_dump_json(),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )