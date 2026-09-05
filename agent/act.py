import json
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.agent import generate_and_execute_stream
from agent.document_generator import generate_document_from_context
from agent.tools.base_knowledge.get_base_knowledge import DB_BRIEF, DB_QUERY_GUIDE, BASE, TARGET, BRIEF_INFO, get_db_query_guide_db, get_base_knowledge_db, base_knowledge_to_str, get_doc_knowledge_db, get_think_knowledge_db, get_code_guide_db
from agent.tools.tools_def import engine, llm
from agent.tools.copilot.utils.call_llm_test import call_llm_stream, call_llm
from agent.tools.copilot.sql_code import parse_selected_fields_json
from agent.tools.search_db import get_db_overview_markdown, search_db_markdown, get_db_summary_for_agent
from agent.tools.search_func import get_func_catalog_markdown, search_func_by_keyword, get_func_summary_for_agent, get_func_docs_for
from agent.tools.get_function_info import FUNCTION_DICT
from agent.tools.web_search.web_search import search_web, fetch_webpage
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
        if act_data.get("schema_detail"):
            entry["schema_detail"] = act_data["schema_detail"]
        if act_data.get("selected_guides"):
            entry["selected_guides"] = act_data["selected_guides"]
        if act_data.get("query_guide_content"):
            entry["query_guide_content"] = act_data["query_guide_content"]
        entries.append(entry)
    elif action == "explore_base_knowledge":
        entry = {"role": "assistant", "type": "act", "action": "explore_base_knowledge"}
        if act_data.get("selected_knowledge_ids") is not None:
            entry["selected_knowledge_ids"] = act_data["selected_knowledge_ids"]
        if act_data.get("knowledge_content"):
            entry["knowledge_content"] = act_data["knowledge_content"]
        if act_data.get("summary"):
            entry["summary"] = act_data["summary"]
        entries.append(entry)
    elif action == "explore_functions":
        entry = {"role": "assistant", "type": "act", "action": "explore_functions"}
        if act_data.get("selected_functions") is not None:
            entry["selected_functions"] = act_data["selected_functions"]
        if act_data.get("func_docs"):
            entry["func_docs"] = act_data["func_docs"]
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
    elif action == "generate_document":
        title = act_data.get("title", "")
        file_name = act_data.get("file_name", "")
        full_text = act_data.get("full_text", "")
        entries.append({"role": "assistant", "type": "act", "action": "generate_document", "title": title, "file_name": file_name, "full_text": full_text})
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
        entry = {"role": "assistant", "type": "act", "action": "fetch_webpage"}
        if act_data.get("display_content"):
            entry["page_content"] = act_data["display_content"]
        elif act_data.get("content"):
            entry["page_content"] = act_data["content"]
        if act_data.get("url"):
            entry["url"] = act_data["url"]
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
    research_guide = params.get("research_guide")

    act_data = {}
    if action == "explore_schema":
        act_data = yield from _act_explore_schema(full_question, session_id, tables, search_keyword)

    elif action == "explore_base_knowledge":
        act_data = yield from _act_explore_base_knowledge(full_question, session_id, search_keyword)

    elif action == "explore_functions":
        act_data = yield from _act_explore_functions(full_question, session_id, search_keyword)

    elif action == "generate_and_execute":
        act_data = yield from _act_generate_and_execute(full_question, session_id, tables, selected_fields, selected_functions, request_json, research_guide)

    elif action == "generate_document":
        title = params.get("title")
        act_data = yield from _act_generate_document(conversation_history, session_id, title, request_json)

    elif action == "web_search":
        act_data = yield from _act_web_search(full_question, session_id, params, request_json)

    elif action == "fetch_webpage":
        act_data = yield from _act_fetch_webpage(full_question, session_id, params, request_json)

    else:
        yield f"data: {json.dumps({'phase': 'act', 'type': 'error', 'content': f'Unknown action: {action}'}, ensure_ascii=False)}\n\n"

    new_entries = _build_act_entries(action, act_data)
    history = None
    if new_entries:
        history = save_session_step(session_id, conversation_history, new_entries)
    if history:
        yield f"data: {json.dumps({'type': 'history', 'history': history}, ensure_ascii=False)}\n\n"


def _act_explore_schema(full_question: str, session_id: str, tables, search_keyword: Optional[str] = None):
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_schema', 'type': 'msg', 'content': '正在搜索数据库信息...'}, ensure_ascii=False)}\n\n"

    base_knowledge = BASE
    full_schema = get_db_overview_markdown(engine, tables, include_samples=True)

    keyword_hint = f"\nFocus hint: {search_keyword.strip()}" if search_keyword and search_keyword.strip() else ""

    prompt = f"""Analyze the following database schema and the user's question to select the relevant tables and columns.

{base_knowledge}

{DB_BRIEF}

{BRIEF_INFO}

{DB_QUERY_GUIDE}

{full_schema}

Context:
{full_question}
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
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_schema', 'type': 'msg', 'content': '正在分析所需字段...'}, ensure_ascii=False)}\n\n"

    error_msg = ""
    for i in range(2):
        if i > 0:
            yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_schema', 'type': 'msg', 'content': '解析失败，正在重新分析...'}, ensure_ascii=False)}\n\n"

        raw = ""
        for chunk in call_llm_stream(prompt + error_msg, llm):
            raw += chunk
            yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_schema', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

        selected_fields = parse_selected_fields_json(raw) or {}
        if selected_fields is not None and isinstance(selected_fields, dict):
            explore_plan = selected_fields.pop("plan", "")
            selected_guide_keys = selected_fields.pop("selected_guides", []) or []
            tables_dict = selected_fields.pop("tables", selected_fields) if "tables" in selected_fields else selected_fields

            if tables_dict and not tables_dict.get("__no_db__") and not selected_fields.get("__no_db__"):
                display_content = get_db_overview_markdown(engine, tables, include_samples=True, selected_fields=tables_dict)
            elif tables_dict and tables_dict.get("__no_db__") or selected_fields.get("__no_db__"):
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
                              token_estimate=len(prompt) // 3)

            yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_schema', 'type': 'done', 'content': display_content, 'result': {'selected_fields': selected_fields, 'db_context': full_schema, 'explore_plan': explore_plan, 'selected_guides': selected_guide_keys, 'query_guide_content': guide_result}, 'search_keyword': search_keyword}, ensure_ascii=False)}\n\n"

            return {"selected_fields": selected_fields, "explore_plan": explore_plan, "schema_detail": display_content, "selected_guides": selected_guide_keys, "query_guide_content": guide_result}

        error_msg = "\n\nPrevious attempt failed to produce valid JSON. Output ONLY a valid JSON object with table names as keys and column lists as values.\n"

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_schema', 'type': 'error', 'content': 'Failed to parse fields after retries'}, ensure_ascii=False)}\n\n"
    return {"selected_fields": {}, "explore_plan": "", "schema_detail": full_schema}


def _act_explore_functions(full_question: str, session_id: str, search_keyword: Optional[str] = None):
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_functions', 'type': 'msg', 'content': '正在搜索函数信息...'}, ensure_ascii=False)}\n\n"

    full_catalog = get_func_catalog_markdown()

    keyword_hint = f"\nFocus hint: {search_keyword.strip()}" if search_keyword and search_keyword.strip() else ""
    func_names = ", ".join(FUNCTION_DICT.keys())
    prompt = f"""Analyze the following function catalog and the user's question to select the needed functions.

{full_catalog}

Context:
{full_question}
{keyword_hint}

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

    return {"selected_functions": selected_functions, "func_docs": display_content}


def _act_explore_base_knowledge(full_question: str, session_id: str, search_keyword: Optional[str] = None):
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_base_knowledge', 'type': 'msg', 'content': '正在搜索基础知识...'}, ensure_ascii=False)}\n\n"

    base_knowledge = get_base_knowledge_db()
    doc_knowledge = get_doc_knowledge_db()
    think_knowledge = get_think_knowledge_db()
    code_guide = get_code_guide_db()

    keyword_hint = f"\nFocus hint: {search_keyword.strip()}" if search_keyword and search_keyword.strip() else ""

    all_knowledge = {}
    all_knowledge.update(base_knowledge)
    all_knowledge.update(doc_knowledge)
    all_knowledge.update(think_knowledge)
    all_knowledge.update(code_guide)

    if not all_knowledge:
        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_base_knowledge', 'type': 'done', 'content': '*(No relevant knowledge found)*', 'result': {'selected_knowledge_ids': [], 'knowledge_content': '', 'summary': ''}, 'search_keyword': search_keyword}, ensure_ascii=False)}\n\n"
        return {"selected_knowledge_ids": [], "knowledge_content": "", "summary": ""}

    knowledge_text = base_knowledge_to_str(all_knowledge)

    prompt = f"""Analyze the following knowledge base and the user's question to select the relevant knowledge entries.

{knowledge_text}

Context:
{full_question}
{keyword_hint}

Output ONLY a JSON object with the following structure:
- "selected_ids": an array of knowledge entry IDs (integers) that are relevant. Empty list if none.
- "summary": a brief summary of which knowledge entries are relevant and why.

Example:
{{"selected_ids": [1, 3, 7], "summary": "The user's question relates to company data analysis, entries 1, 3, 7 provide relevant domain knowledge."}}
"""

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_base_knowledge', 'type': 'msg', 'content': '正在分析相关知识...'}, ensure_ascii=False)}\n\n"

    error_msg = ""
    for i in range(2):
        if i > 0:
            yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_base_knowledge', 'type': 'msg', 'content': '解析失败，正在重新分析...'}, ensure_ascii=False)}\n\n"

        raw = ""
        for chunk in call_llm_stream(prompt + error_msg, llm):
            raw += chunk
            yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_base_knowledge', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

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
                              token_estimate=len(prompt) // 3)

            yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_base_knowledge', 'type': 'done', 'content': display_content, 'result': {'selected_knowledge_ids': selected_ids, 'knowledge_content': display_content, 'summary': summary}, 'search_keyword': search_keyword}, ensure_ascii=False)}\n\n"

            return {"selected_knowledge_ids": selected_ids, "knowledge_content": display_content, "summary": summary}

        error_msg = "\n\nPrevious attempt failed to produce valid JSON. Output ONLY a valid JSON object with 'selected_ids' and 'summary' fields.\n"

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'explore_base_knowledge', 'type': 'error', 'content': 'Failed to parse knowledge selection after retries'}, ensure_ascii=False)}\n\n"
    return {"selected_knowledge_ids": [], "knowledge_content": knowledge_text, "summary": ""}


def _parse_base_knowledge_json(raw: str) -> dict | None:
    from utils.context_trim import parse_json
    result = parse_json(raw)
    if isinstance(result, dict) and "selected_ids" in result:
        return {
            "selected_ids": result.get("selected_ids", []),
            "summary": result.get("summary", ""),
        }
    return None


def _act_generate_and_execute(full_question: str, session_id: str, tables, selected_fields, selected_functions, request_json: str = "", research_guide: str = ""):
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'generate', 'type': 'status', 'content': '正在生成并执行代码...'}, ensure_ascii=False)}\n\n"
    full_code = ""
    full_ans = ""
    exec_error = None
    for event in generate_and_execute_stream(
        full_question, tables, retries=2,
        selected_fields=selected_fields,
        selected_functions=selected_functions,
        research_guide=research_guide,
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


def _act_generate_document(conversation_history, session_id, title: str = "", request_json: str = ""):
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'generate_document', 'type': 'msg', 'content': '正在生成报告文档...'}, ensure_ascii=False)}\n\n"
    last_event = {}
    for event in generate_document_from_context(conversation_history, session_id, title, request_json):
        yield event
        if event.startswith("data: "):
            try:
                last_event = json.loads(event[6:].strip())
            except json.JSONDecodeError:
                pass
    return {
        "title": last_event.get("title", title),
        "file_name": last_event.get("file_name", ""),
        "full_text": last_event.get("content", ""),
        "status": "completed",
    }


def _act_web_search(full_question: str, session_id: str, params: dict, request_json: str = ""):
    query = (params.get("query") or "").strip()
    max_results = params.get("max_results", 10)
    if not query:
        query = full_question.strip()

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'web_search', 'type': 'msg', 'content': f'正在搜索: {query}...'}, ensure_ascii=False)}\n\n"

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
        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'web_search', 'type': 'error', 'content': f'搜索失败: {error_msg}'}, ensure_ascii=False)}\n\n"
        return {"search_results": result_data, "query": query}

    formatted = []
    for r in result_data.get("results", []):
        formatted.append(f"- **{r.get('title', '')}**\n  URL: {r.get('url', '')}\n  {r.get('snippet', '')}")

    display_content = f"## 搜索结果: {query}\n\n共找到 {result_data.get('count', 0)} 条结果:\n\n" + "\n\n".join(formatted)

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'web_search', 'type': 'chunk', 'content': display_content}, ensure_ascii=False)}\n\n"

    log_observe_cycle(session_id, 0, "act", "web_search",
                      prompt=full_question[:5000], response=raw_result[:5000],
                      exec_result=display_content[:10000],
                      token_estimate=len(full_question) // 3)

    record_session_operation(
        session_id, "/api/act/stream/", request_json,
        json.dumps({"query": query, "count": result_data.get("count", 0)}, ensure_ascii=False),
        "success", f"Web search: {query}",
    )

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'web_search', 'type': 'done', 'content': display_content, 'result': {'search_results': result_data, 'query': query}}, ensure_ascii=False)}\n\n"

    return {"search_results": result_data, "query": query, "display_content": display_content}


def _act_fetch_webpage(full_question: str, session_id: str, params: dict, request_json: str = ""):
    url = (params.get("url") or "").strip()
    max_length = params.get("max_length", 10000)
    if not url:
        url = full_question.strip()

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'fetch_webpage', 'type': 'msg', 'content': f'正在获取页面: {url[:100]}...'}, ensure_ascii=False)}\n\n"

    try:
        max_length = min(int(max_length), 50000)
    except (ValueError, TypeError):
        max_length = 10000

    content = fetch_webpage(url, max_length=max_length)
    try:
        parsed = json.loads(content)
        if "error" in parsed:
            error_msg = parsed.get("error", "unknown error")
            yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'fetch_webpage', 'type': 'error', 'content': f'获取页面失败: {error_msg}'}, ensure_ascii=False)}\n\n"
            return {"url": url, "content": content}
    except json.JSONDecodeError:
        pass

    display_content = f"## 页面内容: {url}\n\n{content}\n\n---\n*内容长度: {len(content)} 字符*"

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'fetch_webpage', 'type': 'chunk', 'content': display_content}, ensure_ascii=False)}\n\n"

    log_observe_cycle(session_id, 0, "act", "fetch_webpage",
                      prompt=full_question[:5000], response=content[:5000],
                      exec_result=content[:10000],
                      token_estimate=len(full_question) // 3)

    record_session_operation(
        session_id, "/api/act/stream/", request_json,
        json.dumps({"url": url, "length": len(content)}, ensure_ascii=False),
        "success", f"Fetch webpage: {url[:100]}",
    )

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'fetch_webpage', 'type': 'done', 'content': display_content, 'result': {'url': url, 'content': content[:10000]}}, ensure_ascii=False)}\n\n"

    return {"url": url, "content": content, "display_content": display_content}


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