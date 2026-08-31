import json
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel


from agent.tools.search_db import get_db_summary_for_agent
from agent.tools.search_func import get_func_summary_for_agent
from agent.tools.tools_def import llm
from agent.tools.copilot.utils.call_llm_test import call_llm_stream
from data_access.observe_log import log_observe_cycle
from data_access.session_log import record_session_operation
from agent.tools.tools_def import engine
from utils.front_utils import history_to_text
from utils.context_trim import prepare_trimmed_context, save_session_step, parse_json_raw, parse_json

router = APIRouter()

VALID_ACTIONS = [
    "explore_schema", "explore_functions", "explore_base_knowledge",
    "generate_and_execute",
    "output_text", "ask_question", "ask_choice",
    "summary_and_pause", "attempt_completion",
    "generate_document", "web_search", "fetch_webpage",
]


class ActionInput(BaseModel):
    question: str
    session_id: Optional[str] = None
    conversation_history: Optional[List[dict]] = None
    cycle_index: int = 0


ACTIONS = """

- explore_schema: {{"action": "explore_schema"}}
  Explore the database schema and structure based on previous context. Not used to query data, you should use `generate_and_execute` to exe_sql.
- explore_base_knowledge: {{"action": "explore_base_knowledge", "keyword": "..."}}
  Explore the base knowledge (business domain knowledge, documentation, thinking strategies) based on keyword. Use this to retrieve relevant business context, domain rules, or documentation from the knowledge base.
- explore_functions: {{"action": "explore_functions"}}
  Explore the available function catalog and select needed functions based on previous context.
- generate_and_execute: {{"action": "generate_and_execute", "funcs": ["exe_sql", "load_data"], "research_guide": "..."}}
  Decide to execute code that calls functions. funcs: list of function names to use. The actual code will be generated in the next phase. Do NOT include any code or "code" field in the JSON output.
  research_guide: Optional natural language description of what data to search for and what images/charts to generate. Include details like chart types, data sources, labels, colors, and axis sorting. This guides the code generation phase to produce the correct visualizations. Use this when the task requires specific charts or images. 
- output_text: {{"action": "output_text", "text": "Your response content here..."}}
  Output some text to the user without stopping the pipline.
- ask_question: {{"action": "ask_question", "text": "Your question for the user here..."}}
  Ask the user a question. Use it incase you need some information from user.
- ask_choice: {{"action": "ask_choice", "text": "Your question here...", "choices": ["option1", "option2"]}}
  Give user some choices to choice only one of them.
- summary_and_pause: {{"action": "summary_and_pause", "text": "Your progress summary here..."}}
  Output some text and stop the pipline.
- attempt_completion: {{"action": "attempt_completion", "text": "Your final results here..."}}
  Output some text and stop the pipline in case of completion.
- generate_document: {{"action": "generate_document", "title": "report_title"}}
  Generate a complete business summary document based on the full conversation history. The title specifies the document title. The document will be saved as both .md and .docx files. Use this when the user asks to generate a report or document.
- web_search: {{"action": "web_search", "query": "search query", "max_results": 10}}
  Search the web using DuckDuckGo. Use this when the user asks for real-time information, news, facts, or data not available in the local database. Returns a list of results with title, URL, and snippet. Optionally set max_results (default 10, max 50) to control how many results to return.
- fetch_webpage: {{"action": "fetch_webpage", "url": "https://example.com/page", "max_length": 10000}}
  Fetch and extract the text content of a specific webpage. Use this after `web_search` to read the full content of a promising result. The url should be extracted from a previous search result. max_length controls max characters to return (default 10000).
"""


def _build_action_prompt(
        question: str,
        conversation_history: Optional[List[dict]],
        session_id: str = "",
) -> str:
    trimmed = prepare_trimmed_context(session_id, conversation_history)
    context = ""
    if conversation_history:
        context = history_to_text(trimmed)

    db_summary = get_db_summary_for_agent(engine)
    func_catalog = get_func_summary_for_agent()

    return f"""You are an action decision maker. Given the current context, decide the SINGLE next action to execute.

Some Available Functions:
{func_catalog}
Use `explore_functions` action for more available functions. Then use `generate_and_execute` action to call.

The system is working in Think → Action → Act → Observe cycles. You takes the `Action` part.
Context:
{context if context else '(no context)'}

Output ONLY a valid JSON object on a single line (no md block). Choose from:

{ACTIONS}

Decision Rules:
1. If the plan has an empty todo list, choose ask_question with a polite response to the user.
2. If the plan is complete or no further actions needed, choose attempt_completion.
3. If you need to ask the user something, choose ask_question or ask_choice.
4. If you want to pause and show progress, choose summary_and_pause.
5. `generate_and_execute` is the major action to solve complex problems.
6. `explore_schema` returns all relevant data structure and schema in the database at a time based on previous context. DO NOT try to perform two explore_schema with the same consecutively.
7. `explore_functions` returns all relevant available python function catalog at a time based on previous context. DO NOT try to perform two explore_functions with the same consecutively.
8. `explore_base_knowledge` searches the business domain knowledge base with an optional keyword. Use it to retrieve relevant business rules, domain context, documentation, or thinking strategies. DO NOT perform two explore_base_knowledge consecutively.
9. `web_search` searches the web for real-time information. Use it when the user asks about current events, news, facts, or data that is unlikely to be in the local database.
10. `fetch_webpage` fetches and reads the full text content of a specific URL. Use it after `web_search` to get detailed information from a specific page. The URL should come from a previous search result.

"""


def _event_stream_action(
        question: str,
        session_id: str,
        conversation_history: Optional[List[dict]],
        cycle_index: int,
        request_json: str = "",
):
    prompt = _build_action_prompt(
        question, conversation_history, session_id,
    )

    error_msg = ""
    for i in range(2):
        if i > 0:
            yield f"data: {json.dumps({'phase': 'action', 'type': 'msg', 'content': '解析失败，正在重新决策...'}, ensure_ascii=False)}\n\n"
        else:
            yield f"data: {json.dumps({'phase': 'action', 'type': 'msg', 'content': '正在决策下一步动作...'}, ensure_ascii=False)}\n\n"

        raw = ""
        for chunk in call_llm_stream(prompt + error_msg, llm):
            raw += chunk
            yield f"data: {json.dumps({'phase': 'action', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

        action_result = _parse_action_json(raw)
        action = action_result.get("action")
        if action:
            yield f"data: {json.dumps({'phase': 'action', 'type': 'done', 'content': raw, 'action_result': action_result}, ensure_ascii=False)}\n\n"

            log_observe_cycle(session_id, cycle_index, "action", "decide",
                              prompt=prompt[:5000], response=raw[:5000],
                              token_estimate=len(prompt) // 3)
            record_session_operation(
                session_id, "/api/action/stream/",
                request_json, str(action_result), "",
                "success", f"决定动作: {action}",
                prompt_length=len(prompt)
            )
            history = save_session_step(session_id, conversation_history, [{"role": "assistant", "type": "action_decision", "content": parse_json_raw(raw)}])
            if history:
                yield f"data: {json.dumps({'type': 'history', 'history': history}, ensure_ascii=False)}\n\n"
            return

        error_msg = f"\n\nPrevious attempt failed: {action_result.get('error', 'invalid JSON')}. Output ONLY a single-line JSON object with a valid action field. No markdown code blocks, no extra text, no line breaks.\n"

    record_session_operation(
        session_id, "/api/action/stream/",
        request_json, str(action_result), "",
        "error", action_result.get("error", "未知错误"),
        prompt_length=len(prompt)
    )
    error_content = action_result.get("error", "unknown")
    yield f"data: {json.dumps({'phase': 'action', 'type': 'error', 'content': f'Action failed: {error_content}'}, ensure_ascii=False)}\n\n"


def _parse_action_json(raw: str) -> dict:
    result = parse_json(raw)
    if result is None:
        return {"action": None, "error": f"Failed to parse JSON: {raw.strip()[:200]}"}

    action = result.get("action", "")
    if action not in VALID_ACTIONS:
        return {"action": None, "error": f"Unknown action: {action}", "raw": result}

    return {
        "action": action,
        "keyword": result.get("keyword"),
        "funcs": result.get("funcs"),
        "text": result.get("text"),
        "choices": result.get("choices"),
        "research_guide": result.get("research_guide"),
        "title": result.get("title"),
        "query": result.get("query"),
        "max_results": result.get("max_results"),
        "url": result.get("url"),
        "max_length": result.get("max_length"),
    }


@router.post("/api/action/stream/")
async def action_stream_api(request: Request, user_input: ActionInput):
    return StreamingResponse(
        _event_stream_action(
            user_input.question,
            user_input.session_id or "",
            user_input.conversation_history,
            user_input.cycle_index,
            user_input.model_dump_json(),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
