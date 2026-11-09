import json
import traceback
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.agent import generate_and_execute_stream
from agent.document_generator import generate_document_from_context
from agent.tools.base_knowledge.get_base_knowledge import DB_BRIEF, DB_QUERY_GUIDE, TARGET, MCP_BRIEF, CUSTOM_FUNC_BRIEF, BASE_KNOWLEDGE_BRIEF, get_db_query_guide_db, get_base_knowledge_db, base_knowledge_to_str
from agent.tools.tools_def import engine, llm, read_only_engine
from agent.tools.copilot.sql_code import parse_selected_fields_json
from agent.tools.search_db import get_db_overview_markdown, search_db_markdown, get_db_summary_for_agent
from agent.tools.search_func import get_func_catalog_markdown, search_func_by_keyword, get_func_summary_for_agent, get_func_docs_for
from agent.tools.get_function_info import FUNCTION_DICT
from agent.tools.web_search.web_search import search_web, fetch_webpages
from agent.tools.mcp_client import load_mcp_servers, get_mcp_server, MCPClient, MCPError
from data_access.session_log import record_session_operation
from data_access.observe_log import log_observe_cycle
from utils.front_utils import history_to_text
from utils.context_trim import prepare_trimmed_context, save_session_step, stream_with_context_retry, cap_text
from utils.blackboard import (
    get_blackboard,
    update_blackboard,
    update_code_images,
    blackboard_selected_fields,
    blackboard_section,
    blackboard_input_images,
    normalize_selected_images,
)
from utils.get_config import config_data
from utils.perf_log import perf_api

# Feature toggles — mirror flags in agent/action.py so act.py rejects disabled actions
_ENABLE_MCP = config_data.get('enable_mcp', True)
_ENABLE_BASE_KNOWLEDGE = config_data.get('enable_base_knowledge', True)
_ENABLE_WEB_SEARCH = config_data.get('enable_web_search', True)
_ENABLE_FETCH_URL = config_data.get('enable_fetch_url', True)

# Group 2 ("user interaction") actions. The web frontend renders these locally
# and normally does not call /api/act/stream/ for them, but they are declared in
# `agent/action.py` VALID_ACTIONS and documented as act actions, so the endpoint
# must execute them too (a direct API caller otherwise got "Unknown action" and
# no history entry). Keep this list in sync with FRONTEND_ACTIONS.
_USER_INTERACTION_ACTIONS = (
    "ask_question", "ask_choice", "summary_and_pause", "attempt_completion",
)

_DISABLED_ACTIONS = {}
if not _ENABLE_MCP:
    _DISABLED_ACTIONS["explore_mcp"] = "MCP support is disabled in config"
    _DISABLED_ACTIONS["exe_mcp"] = "MCP support is disabled in config"
if not _ENABLE_BASE_KNOWLEDGE:
    _DISABLED_ACTIONS["explore_base_knowledge"] = "Base knowledge support is disabled in config"
if not _ENABLE_WEB_SEARCH:
    _DISABLED_ACTIONS["web_search"] = "Web search support is disabled in config"
if not _ENABLE_FETCH_URL:
    _DISABLED_ACTIONS["fetch_webpage"] = "Fetch URL support is disabled in config"

router = APIRouter()


class ActInput(BaseModel):
    question: str
    action: str
    session_id: Optional[str] = None
    conversation_history: Optional[List[dict]] = None
    params: Optional[Dict[str, Any]] = None


def _build_context(question: str, conversation_history: Optional[List[dict]], session_id: str = "", level: int = 0):
    trimmed = prepare_trimmed_context(session_id, conversation_history, level=level)
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
        if act_data.get("selected_guides"):
            entry["selected_guides"] = act_data["selected_guides"]
        if act_data.get("parse_failed"):
            entry["error"] = "explore_schema parse failed; previous selection preserved"
        entries.append(entry)
    elif action == "explore_base_knowledge":
        entry = {"role": "assistant", "type": "act", "action": "explore_base_knowledge"}
        if act_data.get("selected_knowledge_ids") is not None:
            entry["selected_knowledge_ids"] = act_data["selected_knowledge_ids"]
        if act_data.get("summary"):
            entry["summary"] = act_data["summary"]
        if act_data.get("parse_failed"):
            entry["error"] = "explore_base_knowledge parse failed; previous selection preserved"
        entries.append(entry)
    elif action == "explore_functions":
        entry = {"role": "assistant", "type": "act", "action": "explore_functions"}
        if act_data.get("selected_functions") is not None:
            entry["selected_functions"] = act_data["selected_functions"]
        if act_data.get("explore_plan"):
            entry["explore_plan"] = act_data["explore_plan"]
        if act_data.get("parse_failed"):
            entry["error"] = "explore_functions parse failed; previous selection preserved"
        entries.append(entry)
    elif action == "generate_and_execute":
        full_code = act_data.get("full_code", "")
        full_ans = act_data.get("full_ans", "")
        exec_error = act_data.get("exec_error")
        images = act_data.get("images") or []
        if exec_error:
            entry = {"role": "assistant", "type": "act", "action": "generate_and_execute", "error": exec_error}
            if full_code:
                entry["code"] = full_code
            if full_ans:
                entry["result"] = full_ans
            if images:
                entry["images"] = images
            entries.append(entry)
        else:
            # Success: always record the entry even when the execution produced
            # no textual output, otherwise Observe never sees that this action
            # ran and the model may repeat the same action in a loop. The
            # `exec_ok` marker lets downstream classification/rendering treat an
            # empty result as a real (permanently kept) execution result.
            entry = {"role": "assistant", "type": "act", "action": "generate_and_execute", "exec_ok": True}
            if full_code:
                entry["code"] = full_code
            entry["result"] = full_ans
            if images:
                entry["images"] = images
            entries.append(entry)
    elif action == "generate_document":
        title = act_data.get("title", "")
        file_name = act_data.get("file_name", "")
        full_text = act_data.get("full_text", "")
        entries.append({"role": "assistant", "type": "act", "action": "generate_document", "title": title, "file_name": file_name, "full_text": full_text, "download_url_md": act_data.get("download_url_md", ""), "download_url_docx": act_data.get("download_url_docx", ""), "download_url_pdf": act_data.get("download_url_pdf", "")})
    elif action == "web_search":
        entry = {"role": "assistant", "type": "act", "action": "web_search"}
        if act_data.get("display_content"):
            entry["search_result"] = act_data["display_content"]
        elif act_data.get("search_results"):
            entry["search_result"] = act_data["search_results"]
        if act_data.get("query"):
            entry["query"] = act_data["query"]
        entries.append(entry)
    elif action == "fetch_webpage":
        pages = act_data.get("pages")
        if pages:
            for p in pages:
                entry = {"role": "assistant", "type": "act", "action": "fetch_webpage",
                         "url": p.get("url", "")}
                entry["page_content"] = f"[Error] {p['error']}" if p.get("error") else p.get("content", "")
                entries.append(entry)
        else:
            entry = {"role": "assistant", "type": "act", "action": "fetch_webpage"}
            if act_data.get("display_content"):
                entry["page_content"] = act_data["display_content"]
            elif act_data.get("content"):
                entry["page_content"] = act_data["content"]
            if act_data.get("url"):
                entry["url"] = act_data["url"]
            entries.append(entry)
    elif action == "explore_mcp":
        entry = {"role": "assistant", "type": "act", "action": "explore_mcp"}
        if act_data.get("selected_tools") is not None:
            entry["selected_tools"] = act_data["selected_tools"]
        if act_data.get("explore_plan"):
            entry["explore_plan"] = act_data["explore_plan"]
        entries.append(entry)
    elif action == "exe_mcp":
        entry = {"role": "assistant", "type": "act", "action": "exe_mcp"}
        if act_data.get("results"):
            entry["results"] = act_data["results"]
        if act_data.get("display_content"):
            entry["display_content"] = act_data["display_content"]
        if act_data.get("error"):
            entry["error"] = act_data["error"]
        entries.append(entry)
    elif action == "select_images":
        entries.append({
            "role": "assistant",
            "type": "act",
            "action": "select_images",
            "selected_images": normalize_selected_images(act_data.get("images")),
        })
    elif action in _USER_INTERACTION_ACTIONS:
        # Documented act entry for Group 2 actions (docs/actions_input_output.md
        # sections 6-9): action + text, plus choices for ask_choice. The
        # interaction semantics (needs_user_input / paused / completed) are
        # carried on the SSE `done` result so the client can drive its loop.
        entry = {"role": "assistant", "type": "act", "action": action, "text": act_data.get("text", "")}
        if action == "ask_choice":
            entry["choices"] = act_data.get("choices", [])
        entries.append(entry)
    return entries


@perf_api(lambda args, kwargs: f"/api/act/stream/:{args[1] if len(args) > 1 else kwargs.get('action', 'unknown')}")
def _event_stream_act(
    question: str,
    action: str,
    session_id: str,
    conversation_history: Optional[List[dict]],
    params: Optional[Dict[str, Any]] = None,
    request_json: str = "",
):
    """Act phase wrapper: turn unexpected errors into a terminal error event.

    Without this guard an unhandled exception closes the SSE stream mid-flight
    and skips the history update, so the caller sees no state change and retries
    the same action forever. Emitting a fatal error event lets the client stop.
    """
    try:
        yield from _event_stream_act_impl(
            question, action, session_id, conversation_history, params, request_json,
        )
    except Exception as e:
        traceback.print_exc()
        message = f"Internal error during `{action}`: {e}"
        yield f"data: {json.dumps({'phase': 'act', 'type': 'error', 'content': message, 'fatal': True}, ensure_ascii=False)}\n\n"
        try:
            entry = {"role": "assistant", "type": "act", "action": action, "error": message}
            history = save_session_step(session_id, conversation_history, [entry])
            if history:
                yield f"data: {json.dumps({'type': 'history', 'history': history}, ensure_ascii=False)}\n\n"
        except Exception:
            traceback.print_exc()


def _event_stream_act_impl(
    question: str,
    action: str,
    session_id: str,
    conversation_history: Optional[List[dict]],
    params: Optional[Dict[str, Any]] = None,
    request_json: str = "",
):
    """Act phase: execute exactly ONE action."""
    def build_question(level):
        return _build_context(question, conversation_history, session_id, level=level)

    full_question = build_question(0)
    params = params or {}
    # The action phase (agent/action.py) forwards the LLM's exploration hint as
    # `keyword` (see the explore_* action descriptions). The bundled frontend
    # renames it to `search_keyword` before calling this endpoint, so accept
    # both names; otherwise a direct API caller that follows the docs would have
    # its hint silently dropped.
    search_keyword = params.get("search_keyword") or params.get("keyword")
    if not isinstance(search_keyword, str):
        search_keyword = None
    tables = params.get("tables")
    selected_fields = params.get("selected_fields")
    research_guide = params.get("research_guide")

    blackboard = get_blackboard(conversation_history)

    def build_blackboard(level):
        return blackboard_section(conversation_history, level=level)

    blackboard_text = build_blackboard(0)
    images = blackboard_input_images(blackboard)
    if not selected_fields or (
        isinstance(selected_fields, dict) and selected_fields.get("__no_db__")
    ):
        board_fields = blackboard_selected_fields(blackboard)
        if board_fields is not None:
            selected_fields = board_fields

    if action in _DISABLED_ACTIONS:
        reason = _DISABLED_ACTIONS[action]
        yield f"data: {json.dumps({'phase': 'act', 'type': 'error', 'content': f'Action `{action}` is not available: {reason}'}, ensure_ascii=False)}\n\n"
        return

    act_data = {}
    if action == "explore_schema":
        act_data = yield from _act_explore_schema(build_question, session_id, tables, search_keyword, build_blackboard, images)

    elif action == "explore_base_knowledge":
        act_data = yield from _act_explore_base_knowledge(build_question, session_id, search_keyword, build_blackboard, images)

    elif action == "explore_functions":
        act_data = yield from _act_explore_functions(build_question, session_id, search_keyword, build_blackboard, images)

    elif action == "generate_and_execute":
        act_data = yield from _act_generate_and_execute(build_question, session_id, tables, selected_fields, request_json, research_guide, blackboard, images)

    elif action == "generate_document":
        title = params.get("title")
        act_data = yield from _act_generate_document(conversation_history, session_id, title, request_json)

    elif action == "web_search":
        act_data = yield from _act_web_search(full_question, session_id, params, request_json)

    elif action == "fetch_webpage":
        act_data = yield from _act_fetch_webpage(full_question, session_id, params, request_json)

    elif action == "explore_mcp":
        act_data = yield from _act_explore_mcp(build_question, session_id, params, request_json, build_blackboard, images)

    elif action == "exe_mcp":
        act_data = yield from _act_exe_mcp(full_question, session_id, params, request_json)

    elif action == "select_images":
        act_data = yield from _act_select_images(session_id, params, request_json)
        if act_data.get("error"):
            entry = {"role": "assistant", "type": "act", "action": "select_images", "error": act_data["error"]}
            history = save_session_step(session_id, conversation_history, [entry])
            if history:
                yield f"data: {json.dumps({'type': 'history', 'history': history}, ensure_ascii=False)}\n\n"
            return

    elif action in _USER_INTERACTION_ACTIONS:
        act_data = yield from _act_user_interaction(action, session_id, params, request_json)

    else:
        yield f"data: {json.dumps({'phase': 'act', 'type': 'error', 'content': f'Unknown action: {action}'}, ensure_ascii=False)}\n\n"

    new_entries = _build_act_entries(action, act_data)
    base_history = update_blackboard(conversation_history, action, act_data)
    history = base_history
    if action == "generate_and_execute":
        history = update_code_images(history, act_data.get("images"))
    if new_entries or history is not conversation_history:
        history = save_session_step(session_id, history, new_entries)
    if history:
        yield f"data: {json.dumps({'type': 'history', 'history': history}, ensure_ascii=False)}\n\n"


def _act_explore_schema(build_question, session_id: str, tables, search_keyword: Optional[str] = None, build_blackboard=None, images=None):
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_schema', 'type': 'msg', 'content': 'Searching database information...'}, ensure_ascii=False)}\n\n"

    full_schema = get_db_overview_markdown(read_only_engine, tables, include_samples=True)

    keyword_hint = f"\nFocus hint: {search_keyword.strip()}" if search_keyword and search_keyword.strip() else ""

    def build_prompt(level):
        return f"""Analyze the following database schema and the user's question to select the relevant tables and columns.

{DB_BRIEF}

{DB_QUERY_GUIDE}

{cap_text(full_schema, level)}

Context:
{build_question(level)}
{build_blackboard(level)}
{keyword_hint}

LANGUAGE IS CRITICAL: The "plan" field text MUST be in the EXACT SAME language as the user's question. If the user asked in Chinese, write the plan in Chinese. If the user asked in English, write the plan in English.

Output ONLY a JSON object with the following structure:
- "tables": an object mapping table names to their needed columns. Use an empty list [] for a table to select all its columns.
- Use {{"tables": {{}}}} to select all tables and all columns.
- Use {{"__no_db__": true}} if no database query is needed or no relevant data in the database.
- "selected_guides": an array of guide IDs (integers) from the SQL Query guide above that are relevant to the query. Empty list if none.
- Include a "plan" field describing the query plan in text.

Example:
```json
{{"tables": {{"users": ["id", "name", "email"], "orders": []}}, "selected_guides": [1, 3, 7], "plan": "Query the users table to get customer IDs and emails, then join with orders table to find purchase records"}}
```
"""
    prompt = build_prompt(0)
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_schema', 'type': 'msg', 'content': 'Analyzing required fields...'}, ensure_ascii=False)}\n\n"

    error_msg = ""
    for i in range(2):
        if i > 0:
            yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_schema', 'type': 'msg', 'content': 'Parsing failed, re-analyzing...'}, ensure_ascii=False)}\n\n"

        raw = ""
        for chunk, reasoning in stream_with_context_retry(lambda lvl: build_prompt(lvl) + error_msg, llm, images=images):
            if chunk:
                raw += chunk
                yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_schema', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
            if reasoning:
                yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_schema', 'type': 'reasoning_chunk', 'content': reasoning}, ensure_ascii=False)}\n\n"

        selected_fields = parse_selected_fields_json(raw)
        if isinstance(selected_fields, dict):
            explore_plan = selected_fields.pop("plan", "")
            selected_guide_keys = selected_fields.pop("selected_guides", []) or []
            tables_dict = selected_fields.pop("tables", selected_fields) if "tables" in selected_fields else selected_fields

            no_db_needed = bool(tables_dict.get("__no_db__")) or bool(selected_fields.get("__no_db__"))
            if tables_dict and not no_db_needed:
                display_content = get_db_overview_markdown(read_only_engine, tables, include_samples=True, selected_fields=tables_dict)
            elif no_db_needed:
                display_content = "*(No database tables needed)*"
            else:
                display_content = full_schema
            selected_fields = tables_dict

            all_guides = get_db_query_guide_db()
            guide_id_set = set(selected_guide_keys)
            guide_result = "\n\n".join(
                f"### {k}\n{v['value']}" for k, v in all_guides.items()
                if v['value'] and v['id'] in guide_id_set
            ) if selected_guide_keys else ""

            log_observe_cycle(session_id, 0, "act", "explore_schema",
                              prompt=prompt[:5000], response=raw[:5000],
                              exec_result=display_content[:10000],
                              token_estimate=len(prompt))

            yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_schema', 'type': 'done', 'content': display_content, 'result': {'selected_fields': selected_fields, 'db_context': full_schema, 'explore_plan': explore_plan, 'selected_guides': selected_guide_keys, 'query_guide_content': guide_result}, 'search_keyword': search_keyword}, ensure_ascii=False)}\n\n"

            return {"selected_fields": selected_fields, "explore_plan": explore_plan, "schema_detail": display_content, "selected_guides": selected_guide_keys, "query_guide_content": guide_result}

        error_msg = "\n\nPrevious attempt failed to produce valid JSON. Output ONLY a valid JSON object with table names as keys and column lists as values.\n"

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_schema', 'type': 'error', 'content': 'Failed to parse fields after retries; keeping previous selection'}, ensure_ascii=False)}\n\n"
    # Parse failure: do NOT overwrite the SCHEMA region with an empty selection,
    # so a previously valid table/column selection is preserved and later code
    # generation is not degraded (mirrors the explore_functions behaviour).
    return {"parse_failed": True, "selected_fields": None, "explore_plan": "", "schema_detail": full_schema}


def _act_explore_functions(build_question, session_id: str, search_keyword: Optional[str] = None, build_blackboard=None, images=None):
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_functions', 'type': 'msg', 'content': 'Searching function information...'}, ensure_ascii=False)}\n\n"

    full_catalog = get_func_catalog_markdown()

    keyword_hint = f"\nFocus hint: {search_keyword.strip()}" if search_keyword and search_keyword.strip() else ""
    func_names = ", ".join(FUNCTION_DICT.keys())

    def build_prompt(level):
        return f"""Analyze the following function catalog and the user's question to select the needed functions.

{CUSTOM_FUNC_BRIEF}

{cap_text(full_catalog, level)}

Context:
{build_question(level)}
{build_blackboard(level)}
{keyword_hint}

Available functions: {func_names}

Output ONLY a JSON object with the following structure:
{{"selected_functions": ["func1", "func2"], "plan": "brief plan describing how these functions will be used"}}

If no functions are needed, return {{"selected_functions": [], "plan": "No functions needed."}}

Example:
{{"selected_functions": ["exe_sql", "get_save_image_path"], "plan": "Execute SQL query then save the resulting image path."}}
"""
    prompt = build_prompt(0)
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_functions', 'type': 'status', 'content': 'Analyzing required functions...'}, ensure_ascii=False)}\n\n"

    error_msg = ""
    raw_text = ""
    selected_functions = None
    explore_plan = ""
    for attempt in range(2):
        if attempt > 0:
            yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_functions', 'type': 'msg', 'content': 'Parsing failed, re-analyzing functions...'}, ensure_ascii=False)}\n\n"

        raw = ""
        for chunk, reasoning in stream_with_context_retry(lambda lvl: build_prompt(lvl) + error_msg, llm, images=images):
            if chunk:
                raw += chunk
                yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_functions', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
            if reasoning:
                yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_functions', 'type': 'reasoning_chunk', 'content': reasoning}, ensure_ascii=False)}\n\n"
        raw_text = raw

        parsed = _parse_function_explore_json(raw)
        if parsed is not None:
            selected_functions = parsed.get("selected_functions", [])
            explore_plan = parsed.get("plan", "")
            break

        error_msg = "\n\nPrevious attempt failed to produce valid JSON. Output ONLY a single JSON object with a 'selected_functions' array (names taken from the catalog above) and a 'plan' string. No markdown code block, no extra text.\n"

    if selected_functions is None:
        # Parse failure: do NOT overwrite the FUNC region with an empty list, so a
        # previous valid selection is preserved and later code generation is not
        # left without any functions or database schema.
        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_functions', 'type': 'error', 'content': 'Failed to parse function selection after retries; keeping previous selection'}, ensure_ascii=False)}\n\n"

        log_observe_cycle(session_id, 0, "act", "explore_functions",
                          prompt=prompt[:5000], response=raw_text[:5000],
                          exec_result="*(parse failed; previous selection preserved)*",
                          token_estimate=len(prompt))

        return {"parse_failed": True, "selected_functions": None, "explore_plan": "", "func_docs": ""}

    if selected_functions:
        display_content = get_func_docs_for(selected_functions)
    else:
        display_content = "*(No functions selected)*"

    log_observe_cycle(session_id, 0, "act", "explore_functions",
                      prompt=prompt[:5000], response=raw_text[:5000],
                      exec_result=display_content[:10000],
                      token_estimate=len(prompt))

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_functions', 'type': 'done', 'content': display_content, 'result': {'selected_functions': selected_functions, 'func_context': full_catalog, 'explore_plan': explore_plan}, 'search_keyword': search_keyword}, ensure_ascii=False)}\n\n"

    return {"selected_functions": selected_functions, "explore_plan": explore_plan, "func_docs": display_content}


def _parse_function_explore_json(raw: str) -> dict | None:
    from utils.context_trim import parse_json
    result = parse_json(raw)
    if not isinstance(result, dict) or "selected_functions" not in result:
        return None
    raw_funcs = result["selected_functions"]
    if not isinstance(raw_funcs, list):
        return None
    valid_func_names = [f.strip() for f in raw_funcs if isinstance(f, str) and f.strip() in FUNCTION_DICT]
    if raw_funcs and not valid_func_names:
        # The model named functions but none exist in the catalog: an empty
        # result here would overwrite the region and poison later code
        # generation, so report a parse failure instead.
        return None
    return {"selected_functions": valid_func_names, "plan": result.get("plan", "")}


def _act_explore_base_knowledge(build_question, session_id: str, search_keyword: Optional[str] = None, build_blackboard=None, images=None):
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_base_knowledge', 'type': 'msg', 'content': 'Searching base knowledge...'}, ensure_ascii=False)}\n\n"

    base_knowledge = get_base_knowledge_db()

    keyword_hint = f"\nFocus hint: {search_keyword.strip()}" if search_keyword and search_keyword.strip() else ""

    all_knowledge = {}
    all_knowledge.update(base_knowledge)

    if not all_knowledge:
        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_base_knowledge', 'type': 'done', 'content': '*(No relevant knowledge found)*', 'result': {'selected_knowledge_ids': [], 'knowledge_content': '', 'summary': ''}, 'search_keyword': search_keyword}, ensure_ascii=False)}\n\n"
        return {"selected_knowledge_ids": [], "knowledge_content": "", "summary": ""}

    knowledge_text = base_knowledge_to_str(all_knowledge)

    def build_prompt(level):
        return f"""Analyze the following knowledge base and the user's question to select the relevant knowledge entries.

{BASE_KNOWLEDGE_BRIEF}

{cap_text(knowledge_text, level)}

Context:
{build_question(level)}
{build_blackboard(level)}
{keyword_hint}

Output ONLY a JSON object with the following structure:
- "selected_ids": an array of knowledge entry IDs (integers) that are relevant. Empty list if none.
- "summary": a brief summary of which knowledge entries are relevant and why.

Example:
{{"selected_ids": [1, 3, 7], "summary": "The user's question relates to company data analysis, entries 1, 3, 7 provide relevant domain knowledge."}}
"""
    prompt = build_prompt(0)

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_base_knowledge', 'type': 'msg', 'content': 'Analyzing relevant knowledge...'}, ensure_ascii=False)}\n\n"

    error_msg = ""
    for i in range(2):
        if i > 0:
            yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_base_knowledge', 'type': 'msg', 'content': 'Parsing failed, re-analyzing...'}, ensure_ascii=False)}\n\n"

        raw = ""
        for chunk, reasoning in stream_with_context_retry(lambda lvl: build_prompt(lvl) + error_msg, llm, images=images):
            if chunk:
                raw += chunk
                yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_base_knowledge', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
            if reasoning:
                yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_base_knowledge', 'type': 'reasoning_chunk', 'content': reasoning}, ensure_ascii=False)}\n\n"

        parsed = _parse_base_knowledge_json(raw)
        if parsed is not None:
            selected_ids = parsed.get("selected_ids", [])
            summary = parsed.get("summary", "")

            id_set = set(selected_ids)
            selected_entries = {k: v for k, v in all_knowledge.items() if v['id'] in id_set}
            display_content = base_knowledge_to_str(selected_entries) if selected_entries else "*(No relevant knowledge selected)*"

            log_observe_cycle(session_id, 0, "act", "explore_base_knowledge",
                              prompt=prompt[:5000], response=raw[:5000],
                              exec_result=display_content[:10000],
                              token_estimate=len(prompt))

            yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_base_knowledge', 'type': 'done', 'content': display_content, 'result': {'selected_knowledge_ids': selected_ids, 'knowledge_content': display_content, 'summary': summary}, 'search_keyword': search_keyword}, ensure_ascii=False)}\n\n"

            return {"selected_knowledge_ids": selected_ids, "knowledge_content": display_content, "summary": summary}

        error_msg = "\n\nPrevious attempt failed to produce valid JSON. Output ONLY a valid JSON object with 'selected_ids' and 'summary' fields.\n"

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_base_knowledge', 'type': 'error', 'content': 'Failed to parse knowledge selection after retries; keeping previous selection'}, ensure_ascii=False)}\n\n"
    # Parse failure: do NOT overwrite the KNOWLEDGE region with an empty
    # selection, so a previously valid selection is preserved (mirrors the
    # explore_schema / explore_functions behaviour).
    return {"parse_failed": True, "selected_knowledge_ids": None, "knowledge_content": knowledge_text, "summary": ""}


def _parse_base_knowledge_json(raw: str) -> dict | None:
    from utils.context_trim import parse_json
    result = parse_json(raw)
    if isinstance(result, dict) and "selected_ids" in result:
        return {
            "selected_ids": result.get("selected_ids", []),
            "summary": result.get("summary", ""),
        }
    return None


def _act_generate_and_execute(build_question, session_id: str, tables, selected_fields, request_json: str = "", research_guide: str = "", blackboard=None, images=None):
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'generate', 'type': 'status', 'content': 'Generating and executing code...'}, ensure_ascii=False)}\n\n"
    full_question = build_question(0)
    full_code = ""
    full_ans = ""
    exec_error = None
    generated_images = []
    for event in generate_and_execute_stream(
        full_question, tables, retries=2,
        selected_fields=selected_fields,
        research_guide=research_guide,
        blackboard=blackboard,
        images=images,
        question_builder=build_question,
    ):
        if event.get("sub_type") == "code_chunk":
            if exec_error:
                full_code = ""
                full_ans = ""
                exec_error = None
                generated_images = []
            full_code += event.get("content", "")
        if event.get("sub_type") == "code_complete":
            full_code = event.get("content", "")
        if event.get("sub_type") == "exec_chunk":
            full_ans += event.get("content", "")
        if event.get("sub_type") == "code_exe_error":
            exec_error = event.get("content", "")
        if event.get("sub_type") == "code_gen_error":
            exec_error = event.get("content", "")
        if event.get("type") == "error":
            exec_error = event.get("content", exec_error or "code generation/execution failed")

        if event.get("type") == "done" and event.get("sub_phase") == "exec":
            full_code = event.get("code", full_code)
            full_ans = event.get("content", full_ans)
            generated_images = event.get("images", generated_images)
            event = {
                **event,
                "result": {
                    "code": full_code,
                    "exec_result": full_ans,
                    "error": exec_error,
                    "images": generated_images,
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

    return {"full_code": full_code, "full_ans": full_ans, "exec_error": exec_error, "images": generated_images}


def _act_generate_document(conversation_history, session_id, title: str = "", request_json: str = ""):
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'generate_document', 'type': 'msg', 'content': 'Generating report document...'}, ensure_ascii=False)}\n\n"
    last_event = {}
    for event in generate_document_from_context(conversation_history, session_id, title, request_json):
        yield event
        if event.startswith("data: "):
            try:
                last_event = json.loads(event[6:].strip())
            except json.JSONDecodeError:
                pass
    file_name = last_event.get("file_name", "")
    if file_name:
        static_url = config_data["static_path"].rstrip("/")
        static_folder = "tmp_imgs"
        download_url_md = f"{static_url}/{static_folder}/{file_name}.md"
        download_url_docx = f"{static_url}/{static_folder}/{file_name}.docx"
        download_url_pdf = f"{static_url}/{static_folder}/{file_name}.pdf"
    else:
        download_url_md = download_url_docx = download_url_pdf = ""
    return {
        "title": last_event.get("title", title),
        "file_name": file_name,
        "full_text": last_event.get("content", ""),
        "download_url_md": download_url_md,
        "download_url_docx": download_url_docx,
        "download_url_pdf": download_url_pdf,
        "status": "completed",
    }


def _act_web_search(full_question: str, session_id: str, params: dict, request_json: str = ""):
    query = (params.get("query") or "").strip()
    max_results = params.get("max_results", 10)
    if not query:
        query = full_question.strip()

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'web_search', 'type': 'msg', 'content': f'Searching: {query}...'}, ensure_ascii=False)}\n\n"

    try:
        max_results = min(int(max_results), 50)
    except (ValueError, TypeError):
        max_results = 10

    raw_result = search_web(query, max_results=max_results)
    try:
        result_data = json.loads(raw_result)
    except json.JSONDecodeError:
        result_data = {"error": "Failed to parse search results", "raw": raw_result}

    if "error" in result_data:
        error_msg = result_data.get("error", "unknown error")
        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'web_search', 'type': 'error', 'content': f'Search failed: {error_msg}'}, ensure_ascii=False)}\n\n"
        return {"search_results": result_data, "query": query}

    formatted = []
    for r in result_data.get("results", []):
        formatted.append(f"- **{r.get('title', '')}**\n  URL: {r.get('url', '')}\n  {r.get('snippet', '')}")

    display_content = f"## Search Results: {query}\n\nFound {result_data.get('count', 0)} results:\n\n" + "\n\n".join(formatted)

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'web_search', 'type': 'chunk', 'content': display_content}, ensure_ascii=False)}\n\n"

    log_observe_cycle(session_id, 0, "act", "web_search",
                      prompt=full_question[:5000], response=raw_result[:5000],
                      exec_result=display_content[:10000],
                      token_estimate=len(full_question))

    record_session_operation(
        session_id, "/api/act/stream/", request_json,
        ans=json.dumps({"query": query, "count": result_data.get("count", 0)}, ensure_ascii=False),
        result_type="success", msg=f"Web search: {query}",
    )

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'web_search', 'type': 'done', 'content': display_content, 'result': {'search_results': result_data, 'query': query}}, ensure_ascii=False)}\n\n"

    return {"search_results": result_data, "query": query, "display_content": display_content}


def _act_fetch_webpage(full_question: str, session_id: str, params: dict, request_json: str = ""):
    # Accept {"urls": [...]} (new, parallel) or {"url": "..."} (single / legacy).
    raw_urls = params.get("urls")
    urls = [u.strip() for u in raw_urls if isinstance(u, str) and u.strip()] if isinstance(raw_urls, list) else []
    if not urls:
        single = (params.get("url") or "").strip()
        if single:
            urls = [single]
    if not urls:
        urls = [full_question.strip()]
    urls = urls[:10]

    max_length = params.get("max_length", 10000)
    try:
        max_length = min(int(max_length), 50000)
    except (ValueError, TypeError):
        max_length = 10000

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'fetch_webpage', 'type': 'msg', 'content': f'Fetching {len(urls)} page(s) in parallel...'}, ensure_ascii=False)}\n\n"

    raw = fetch_webpages(urls, max_length=max_length)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"results": []}
    pages = data.get("results") or []

    sections = []
    for p in pages:
        if p.get("error"):
            sections.append(f"## {p.get('url', '')}\n\n> Failed: {p.get('error')}")
        else:
            sections.append(f"## {p.get('url', '')}\n\n{p.get('content', '')}")
    display_content = f"## Page Content ({len(pages)} page(s))\n\n" + "\n\n---\n\n".join(sections)

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'fetch_webpage', 'type': 'chunk', 'content': display_content}, ensure_ascii=False)}\n\n"

    log_observe_cycle(session_id, 0, "act", "fetch_webpage",
                      prompt=full_question[:5000], response=display_content[:5000],
                      exec_result=display_content[:10000],
                      token_estimate=len(full_question))

    record_session_operation(
        session_id, "/api/act/stream/", request_json,
        ans=json.dumps({"urls": urls, "count": len(pages)}, ensure_ascii=False),
        result_type="success", msg=f"Fetch webpages: {len(urls)}",
    )

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'fetch_webpage', 'type': 'done', 'content': display_content, 'result': {'urls': urls, 'url': urls[0] if urls else '', 'pages': pages, 'content': display_content[:10000]}}, ensure_ascii=False)}\n\n"

    return {"pages": pages, "urls": urls, "display_content": display_content}


def _act_explore_mcp(build_question, session_id: str, params: dict, request_json: str = "", build_blackboard=None, images=None):
    # Accept both `search_keyword` (frontend) and `keyword` (action phase / docs).
    raw_keyword = params.get("search_keyword") or params.get("keyword")
    search_keyword = raw_keyword.strip() if isinstance(raw_keyword, str) else ""

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_mcp', 'type': 'msg', 'content': 'Connecting to MCP servers to fetch tool list...'}, ensure_ascii=False)}\n\n"

    all_servers_config = load_mcp_servers()
    if not all_servers_config:
        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_mcp', 'type': 'error', 'content': 'No MCP servers configured'}, ensure_ascii=False)}\n\n"
        return {"selected_tools": [], "catalog": "", "tool_detail": "", "explore_plan": "", "error": "No MCP servers configured"}

    all_tools = []
    failed_servers = []
    for srv in all_servers_config:
        name = srv.get("name", "?")
        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_mcp', 'type': 'msg', 'content': f'Listing tools from MCP server: {name}...'}, ensure_ascii=False)}\n\n"
        try:
            with MCPClient(srv) as client:
                tools = client.list_tools()
                if tools:
                    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_mcp', 'type': 'msg', 'content': f'Found {len(tools)} tools from {name}'}, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_mcp', 'type': 'msg', 'content': f'No tools available from {name}'}, ensure_ascii=False)}\n\n"
                for t in tools:
                    t["_server"] = name
                    all_tools.append(t)
        except Exception as e:
            yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_mcp', 'type': 'msg', 'content': f'Failed to connect to {name}: {e}'}, ensure_ascii=False)}\n\n"
            failed_servers.append(f"{name}({e})")

    if not all_tools:
        err = "All MCP servers failed to connect: " + ", ".join(failed_servers) if failed_servers else "No MCP servers provided any tools"
        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_mcp', 'type': 'error', 'content': err}, ensure_ascii=False)}\n\n"
        return {"selected_tools": [], "catalog": "", "tool_detail": "", "explore_plan": "", "error": err}

    catalog_lines = ["## MCP Tool Catalog\n"]
    for t in all_tools:
        srv = t.get("_server", "?")
        schema = t.get("inputSchema", {})
        params_str = ""
        if schema and schema.get("properties"):
            props = []
            for pn, pi in schema["properties"].items():
                req = pn in (schema.get("required", []))
                props.append(f"`{pn}`({pi.get('type','any')}){'required' if req else ''}:{pi.get('description','')}")
            params_str = " [" + "; ".join(props) + "]"
        catalog_lines.append(f"- **{srv}/{t['name']}**: {t.get('description', '')}{params_str}")
    catalog = "\n".join(catalog_lines)

    keyword_hint = f"\nFocus hint: {search_keyword.strip()}" if search_keyword else ""

    mcp_brief = str(MCP_BRIEF)

    def build_prompt(level):
        return f"""Analyze the following MCP tool catalog and the user's question to select the relevant tools.

{mcp_brief}

{cap_text(catalog, level)}

Context:
{build_question(level)}
{build_blackboard(level)}
{keyword_hint}

Output ONLY a JSON object with the following structure:
- "selected_tools": an array of objects with "server" and "name" fields identifying which tools to use.
- "plan": a brief plan describing how these tools will be used.

Example:
{{"selected_tools": [{{"server": "calculator", "name": "calculate"}}], "plan": "Use calculator to evaluate math expressions."}}

If no tools are needed, return {{"selected_tools": [], "plan": "No MCP tools needed."}}
"""
    prompt = build_prompt(0)
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_mcp', 'type': 'msg', 'content': 'Analyzing required MCP tools...'}, ensure_ascii=False)}\n\n"

    # Parse-retry loop, matching the other explore_* actions: a single bad JSON
    # reply previously ended the phase with no selection. ``stream_with_context_retry``
    # still handles context-length overflow inside each attempt.
    raw = ""
    selected_tools = []
    explore_plan = ""
    error_msg = ""
    for attempt in range(2):
        if attempt > 0:
            yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_mcp', 'type': 'msg', 'content': 'Parsing failed, re-analyzing MCP tools...'}, ensure_ascii=False)}\n\n"

        raw = ""
        for chunk, reasoning in stream_with_context_retry(lambda lvl: build_prompt(lvl) + error_msg, llm, images=images):
            if chunk:
                raw += chunk
                yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_mcp', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
            if reasoning:
                yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_mcp', 'type': 'reasoning_chunk', 'content': reasoning}, ensure_ascii=False)}\n\n"

        parsed = _parse_mcp_explore_json(raw)
        if parsed is not None:
            selected_tools = parsed.get("selected_tools", []) or []
            explore_plan = parsed.get("plan", "")
            break

        error_msg = "\n\nPrevious attempt failed to produce valid JSON. Output ONLY a single JSON object with a 'selected_tools' array (objects with 'server' and 'name') and a 'plan' string. No markdown code block, no extra text.\n"

    if selected_tools:
        selected_lines = ["## Selected MCP Tools\n"]
        for st in selected_tools:
            svr = st.get("server", "")
            name = st.get("name", "")
            matching = [t for t in all_tools if t.get("_server") == svr and t.get("name") == name]
            if matching:
                t = matching[0]
                schema = t.get("inputSchema", {})
                params_str = ""
                if schema and schema.get("properties"):
                    props = []
                    for pn, pi in schema["properties"].items():
                        req = pn in (schema.get("required", []))
                        props.append(f"`{pn}`({pi.get('type','any')}){'required' if req else ''}:{pi.get('description','')}")
                    params_str = " [" + "; ".join(props) + "]"
                selected_lines.append(f"- **{svr}/{name}**: {t.get('description', '')}{params_str}")
        tool_detail = "\n".join(selected_lines)
    else:
        tool_detail = "*(No tools selected)*"

    log_observe_cycle(session_id, 0, "act", "explore_mcp",
                      prompt=prompt[:5000], response=raw[:5000],
                      exec_result=tool_detail[:10000],
                      token_estimate=len(prompt))

    record_session_operation(
        session_id, "/api/act/stream/", request_json,
        ans=json.dumps({"servers_count": len(all_servers_config), "tools_count": len(all_tools), "selected_count": len(selected_tools)}, ensure_ascii=False),
        result_type="success", msg=f"Explore MCP: {len(all_tools)} tools from {len(all_servers_config)} servers",
    )

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_mcp', 'type': 'done', 'content': tool_detail, 'result': {'selected_tools': selected_tools, 'catalog': catalog, 'explore_plan': explore_plan}, 'search_keyword': search_keyword}, ensure_ascii=False)}\n\n"

    return {"selected_tools": selected_tools, "explore_plan": explore_plan, "tool_detail": tool_detail, "catalog": catalog}


def _parse_mcp_explore_json(raw: str) -> dict | None:
    from utils.context_trim import parse_json
    result = parse_json(raw)
    if isinstance(result, dict) and "selected_tools" in result:
        return result
    return None


def _execute_single_mcp_tool(server_name: str, tool_name: str, tool_params: dict) -> dict:
    """Execute a single MCP tool and return the result dict."""
    server_config = get_mcp_server(server_name)
    if not server_config:
        raise ValueError(f"MCP server not found: {server_name}")

    with MCPClient(server_config) as client:
        return client.call_tool(tool_name, tool_params)


def _format_mcp_result(server_name: str, tool_name: str, result: dict) -> str:
    """Format MCP tool result into display text."""
    result_content = result.get("content", [])
    result_text_parts = []
    for part in result_content:
        if isinstance(part, dict):
            if part.get("type") == "text":
                result_text_parts.append(part.get("text", ""))
            elif part.get("type") == "resource":
                resource = part.get("resource", {})
                result_text_parts.append(f"[Resource] {resource.get('text', '')}")
        else:
            result_text_parts.append(str(part))
    result_text = "\n".join(result_text_parts) if result_text_parts else json.dumps(result, ensure_ascii=False, indent=2)
    return f"### {server_name}/{tool_name}\n\n{result_text}"


def _act_select_images(session_id: str, params: dict, request_json: str = ""):
    raw_images = params.get("images")
    if raw_images is None:
        raw_images = params.get("selected_images")

    if not isinstance(raw_images, list):
        err = "select_images requires an `images` array"
        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'select_images', 'type': 'error', 'content': err}, ensure_ascii=False)}\n\n"
        return {"error": err}

    images = normalize_selected_images(raw_images)
    if raw_images and not images:
        err = "select_images received no valid image entries (each needs a path and reason)"
        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'select_images', 'type': 'error', 'content': err}, ensure_ascii=False)}\n\n"
        return {"error": err}

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'select_images', 'type': 'msg', 'content': f'Updating selected images ({len(images)})...'}, ensure_ascii=False)}\n\n"

    if images:
        display_content = "## Selected Images\n\n" + "\n".join(
            f"- {item['path']}: {item['reason'] or '(no reason)'}" for item in images
        )
    else:
        display_content = "## Selected Images\n\n(none)"

    log_observe_cycle(session_id, 0, "act", "select_images",
                      prompt="", response=json.dumps({"images": images}, ensure_ascii=False)[:5000],
                      token_estimate=0)
    record_session_operation(
        session_id, "/api/act/stream/", request_json,
        ans=json.dumps({"images": images}, ensure_ascii=False),
        result_type="success", msg=f"Selected images: {len(images)}",
    )

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'select_images', 'type': 'chunk', 'content': display_content}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'select_images', 'type': 'done', 'content': display_content, 'result': {'selected_images': images}}, ensure_ascii=False)}\n\n"

    return {"images": images}


def _act_user_interaction(action: str, session_id: str, params: dict, request_json: str = ""):
    """Execute a Group 2 (user interaction) action: ask_question / ask_choice /
    summary_and_pause / attempt_completion.

    These actions do not call any tool; they surface ``params["text"]`` (and
    ``params["choices"]`` for ask_choice) to the user and stop the loop. They
    were previously handled only in the web frontend, so calling
    ``/api/act/stream/`` directly with one of them returned an "Unknown action"
    error and wrote no history entry. Handling them here makes the endpoint match
    ``agent/action.py`` / ``docs/actions_input_output.md`` and keeps a single
    authoritative implementation.
    """
    text = params.get("text") or ""
    if not isinstance(text, str):
        text = str(text)
    choices = params.get("choices") or []
    if not isinstance(choices, list):
        choices = []

    needs_user_input = action in ("ask_question", "ask_choice")
    paused = action == "summary_and_pause"
    completed = action == "attempt_completion"

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': action, 'type': 'msg', 'content': f'Presenting {action}...'}, ensure_ascii=False)}\n\n"

    result = {
        "action": action,
        "text": text,
        "choices": choices,
        "needs_user_input": needs_user_input,
        "paused": paused,
        "completed": completed,
    }

    log_observe_cycle(session_id, 0, "act", action,
                      prompt="", response=json.dumps(result, ensure_ascii=False)[:5000],
                      token_estimate=0)
    record_session_operation(
        session_id, "/api/act/stream/", request_json,
        ans=json.dumps(result, ensure_ascii=False),
        result_type="success", msg=f"{action}: {text[:100]}",
    )

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': action, 'type': 'chunk', 'content': text}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': action, 'type': 'done', 'content': text, 'result': result}, ensure_ascii=False)}\n\n"

    return {"action": action, "text": text, "choices": choices}


def _act_exe_mcp(full_question: str, session_id: str, params: dict, request_json: str = ""):
    tools_list = params.get("tools") or []

    # Backward compatible: single tool format (server/tool/params)
    if not tools_list:
        server_name = (params.get("server") or "").strip()
        tool_name = (params.get("tool") or "").strip()
        tool_params = params.get("params") or {}
        if server_name and tool_name:
            tools_list = [{"server": server_name, "tool": tool_name, "params": tool_params}]

    if not tools_list:
        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'exe_mcp', 'type': 'error', 'content': 'MCP tools are required: provide a tools array or server/tool/params fields'}, ensure_ascii=False)}\n\n"
        return {"results": [], "display_content": "", "error": "No tools specified"}

    all_results = []
    all_displays = []
    has_error = False

    for i, tool_spec in enumerate(tools_list):
        server_name = (tool_spec.get("server") or "").strip()
        tool_name = (tool_spec.get("tool") or "").strip()
        tool_params = tool_spec.get("params") or {}

        if not server_name or not tool_name:
            err_msg = f"Tool #{i + 1} is missing server or tool name"
            yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'exe_mcp', 'type': 'error', 'content': err_msg}, ensure_ascii=False)}\n\n"
            all_results.append({"server": server_name, "tool": tool_name, "error": err_msg})
            has_error = True
            continue

        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'exe_mcp', 'type': 'msg', 'content': f'Executing MCP tool [{i + 1}/{len(tools_list)}]: {server_name}/{tool_name}...'}, ensure_ascii=False)}\n\n"

        try:
            yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'exe_mcp', 'type': 'msg', 'content': f'Calling {tool_name}...'}, ensure_ascii=False)}\n\n"
            result = _execute_single_mcp_tool(server_name, tool_name, tool_params)
        except MCPError as e:
            yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'exe_mcp', 'type': 'error', 'content': f'MCP call failed: {server_name}/{tool_name}: {e}'}, ensure_ascii=False)}\n\n"
            all_results.append({"server": server_name, "tool": tool_name, "error": str(e)})
            all_displays.append(f"### {server_name}/{tool_name}\n\n**Error:** {e}")
            has_error = True
            continue
        except Exception as e:
            yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'exe_mcp', 'type': 'error', 'content': f'MCP call failed: {server_name}/{tool_name}: {e}'}, ensure_ascii=False)}\n\n"
            all_results.append({"server": server_name, "tool": tool_name, "error": str(e)})
            all_displays.append(f"### {server_name}/{tool_name}\n\n**Error:** {e}")
            has_error = True
            continue

        display = _format_mcp_result(server_name, tool_name, result)
        all_results.append({"server": server_name, "tool": tool_name, "result": result})
        all_displays.append(display)

        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'exe_mcp', 'type': 'chunk', 'content': display}, ensure_ascii=False)}\n\n"

    log_text = "; ".join(f"{r['server']}/{r['tool']}" for r in all_results)
    result_text = "\n\n".join(all_displays) if all_displays else "(no results)"

    combined_display = f"## MCP Tool Execution Results\n\n{result_text}"

    log_observe_cycle(session_id, 0, "act", "exe_mcp",
                      prompt=full_question[:5000], response=result_text[:5000],
                      token_estimate=len(full_question))

    status = "success" if not has_error else "partial"
    record_session_operation(
        session_id, "/api/act/stream/", request_json,
        ans=json.dumps({"tools_count": len(tools_list), "results": [{"server": r.get("server"), "tool": r.get("tool")} for r in all_results]}, ensure_ascii=False),
        result_type=status, msg=f"Execute MCP: {log_text}",
    )

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'exe_mcp', 'type': 'done', 'content': combined_display, 'result': {'results': all_results, 'combined_display': combined_display}}, ensure_ascii=False)}\n\n"

    return {"results": all_results, "display_content": combined_display}


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