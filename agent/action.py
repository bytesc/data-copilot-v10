import json
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.tools.base_knowledge.get_base_knowledge import BRIEF_INFO
from agent.tools.search_db import get_db_summary_for_agent
from agent.tools.search_func import get_func_summary_for_agent
from agent.tools.tools_def import llm
from agent.tools.copilot.utils.call_llm_test import call_llm_stream_with_reasoning
from data_access.observe_log import log_observe_cycle, log_observe_session
from data_access.session_log import record_session_operation
from agent.tools.tools_def import engine
from utils.front_utils import history_to_text
from utils.blackboard import blackboard_section, blackboard_input_images_from_history
from utils.context_trim import prepare_trimmed_context, save_session_step, parse_json_raw, parse_json
from utils.get_config import config_data
from utils.perf_log import perf_api

router = APIRouter()

ENABLE_MCP = config_data.get('enable_mcp', True)
ENABLE_BASE_KNOWLEDGE = config_data.get('enable_base_knowledge', True)
ENABLE_WEB_SEARCH = config_data.get('enable_web_search', True)
ENABLE_FETCH_URL = config_data.get('enable_fetch_url', True)

VALID_ACTIONS = [
    "explore_schema", "explore_functions",
    "generate_and_execute",
    "ask_question", "ask_choice",
    "summary_and_pause", "attempt_completion",
    "generate_document",
    "select_images",
]
if ENABLE_BASE_KNOWLEDGE:
    VALID_ACTIONS.append("explore_base_knowledge")
if ENABLE_WEB_SEARCH:
    VALID_ACTIONS.append("web_search")
if ENABLE_FETCH_URL:
    VALID_ACTIONS.append("fetch_webpage")
if ENABLE_MCP:
    VALID_ACTIONS.extend(["explore_mcp", "exe_mcp"])


class ActionInput(BaseModel):
    question: str
    session_id: Optional[str] = None
    conversation_history: Optional[List[dict]] = None
    cycle_index: int = 0


_ACTION_DESCRIPTIONS = {
    "explore_schema": """- explore_schema: {"action": "explore_schema", "keyword": "..."}
  Explore the database schema and structure. Optional keyword hints the LLM to focus on specific tables/columns. Running it writes/overwrites the DB region of the blackboard; re-run it when the user's data requirements change. Not used to query data, you should use `generate_and_execute` to exe_sql.""",
    "explore_functions": """- explore_functions: {"action": "explore_functions", "keyword": "..."}
  Explore the available function catalog. Optional keyword hints the LLM to focus on relevant functions. Running it writes/overwrites the FUNC region of the blackboard; re-run it when the user's requirements change. Use `explore_functions` for more available functions. Then use `generate_and_execute` action to call.""",
    "generate_and_execute": """- generate_and_execute: {"action": "generate_and_execute", "research_guide": "..."}
  Decide to execute code that calls functions. The function names are read from the FUNC region of the blackboard (selected by `explore_functions`); do NOT include a "funcs" field. The actual code will be generated in the next phase. Do NOT include any code or "code" field in the JSON output.
  research_guide: Optional natural language description of what data to search for and what images/charts to generate. Include details like chart types, data sources, labels, colors, and axis sorting. This guides the code generation phase to produce the correct visualizations. Use this when the task requires specific charts or images. If the user only asks to view, observe, or describe an existing image, do NOT regenerate it; use `select_images` with the exact existing filename instead.""",
    "ask_question": """- ask_question: {"action": "ask_question", "text": "Your question for the user here..."}
  Ask the user a question. Use it incase you need some information from user.""",
    "ask_choice": """- ask_choice: {"action": "ask_choice", "text": "Your question here...", "choices": ["option1", "option2"]}
  Give user some choices to choice only one of them.""",
    "summary_and_pause": """- summary_and_pause: {"action": "summary_and_pause", "text": "Your progress summary here..."}
  Output some text and stop the pipline.""",
    "attempt_completion": """- attempt_completion: {"action": "attempt_completion", "text": "Your final results here..."}
  Output some text and stop the pipline in case of completion.""",
    "generate_document": """- generate_document: {"action": "generate_document", "title": "report_title"}
  Generate a complete business summary document based on the full conversation history. The title specifies the document title. The document will be saved as both .md and .docx files. Use this when the user asks to generate a report or document.""",
    "select_images": """- select_images: {"action": "select_images", "images": [{"path": "local_filename.png", "reason": "one sentence explaining why this image is selected"}, {"path": "https://example.com/chart.png", "reason": "one sentence explaining why this image is selected"}]}
  Select the images that should stay in the SELECTED IMAGES region of the blackboard. Each item needs `path` (a local image filename saved under tmp_imgs, or a full http(s) image URL) and a one-sentence `reason`. Valid candidates include images in the current IMAGES region, images generated in earlier turns of this conversation, images attached to the conversation, and image URLs present in the context; never invent image paths. The IMAGES region only keeps the most recent code execution's images, so an image generated earlier remains selectable even when it is no longer listed there - do not tell the user an earlier generated image is gone or unselectable merely because it is absent from the current IMAGES region. Earlier generated images often appear as markdown image URLs in previous `generate_and_execute` results; extract the filename from the URL (e.g. `.../tmp_imgs/xxx.png` -> `xxx.png`) and use that as `path`. If the user refers to an earlier image by position or description (e.g. "the second image"), resolve it from earlier turns and select its filename instead of asking the user to regenerate it. When the user asks to view, observe, or describe an image, selecting it with `select_images` is the required first action; only describe the image in a later cycle after it has been selected. Re-running overwrites the whole region. The selected images are attached to later LLM calls after the images generated by the last code execution. Use it to keep the most relevant charts/reference images for the current task. When the user's requirements change (new scope, new analysis target, or a correction), re-run `select_images` to update this region instead of keeping stale selections. Do not call it again when the current SELECTED IMAGES region already contains exactly the same paths. It can be batched with explore actions, but NEVER with user-interaction actions such as ask_question, ask_choice, summary_and_pause, or attempt_completion.""",
}

if ENABLE_BASE_KNOWLEDGE:
    _ACTION_DESCRIPTIONS["explore_base_knowledge"] = """- explore_base_knowledge: {"action": "explore_base_knowledge", "keyword": "..."}
  Explore the base knowledge (business domain knowledge, documentation, thinking strategies). Optional keyword hints the LLM to focus on specific knowledge entries. Running it writes/overwrites the KNOWLEDGE region of the blackboard; re-run it when the user's requirements or domain context change. Use this to retrieve relevant business context, domain rules, or documentation from the knowledge base."""

if ENABLE_WEB_SEARCH:
    _ACTION_DESCRIPTIONS["web_search"] = """- web_search: {"action": "web_search", "query": "search query", "max_results": 10}
  Search the web using DuckDuckGo. Use this when the user asks for real-time information, news, facts, or data not available in the local database. Returns a list of results with title, URL, and snippet. Optionally set max_results (default 10, max 50) to control how many results to return."""

if ENABLE_FETCH_URL:
    _ACTION_DESCRIPTIONS["fetch_webpage"] = """- fetch_webpage: {"action": "fetch_webpage", "url": "https://example.com/page", "max_length": 10000}
   Fetch and extract the text content of a specific webpage. Use this after `web_search` to read the full content of a promising result. The url should be extracted from a previous search result. max_length controls max characters to return (default 10000)."""

if ENABLE_MCP:
    _ACTION_DESCRIPTIONS["explore_mcp"] = """- explore_mcp: {"action": "explore_mcp", "keyword": "..."}
   Explore available tools from all configured MCP (Model Context Protocol) servers. Optional keyword hints the LLM to focus on relevant tools. Running it writes/overwrites the MCP region of the blackboard; re-run it when the user's requirements change. Returns a list of available tools with their server, descriptions and parameter schemas. Use this to discover what capabilities MCP servers offer. Then use `exe_mcp` action to call a specific tool."""
    _ACTION_DESCRIPTIONS["exe_mcp"] = """- exe_mcp: {"action": "exe_mcp", "server": "server_name", "tool": "tool_name", "params": {"key": "value"}}
   Execute one or more tools on MCP servers. Single tool format: use "server", "tool", "params" fields. Multi-tool format: use "tools" array:
   {"action": "exe_mcp", "tools": [{"server": "...", "tool": "...", "params": {...}}, ...]}
   All tools are executed sequentially and results are returned together."""

ACTIONS_BODY = "\n\n".join(_ACTION_DESCRIPTIONS[a] for a in VALID_ACTIONS)

_GROUP_1_ACTIONS = ["explore_schema", "explore_functions", "select_images"]
if ENABLE_BASE_KNOWLEDGE:
    _GROUP_1_ACTIONS.append("explore_base_knowledge")
if ENABLE_MCP:
    _GROUP_1_ACTIONS.append("explore_mcp")

_GROUP_2_ACTIONS = ["ask_question", "ask_choice", "summary_and_pause", "attempt_completion"]

_OTHER_ACTIONS = ["generate_and_execute", "generate_document"]
if ENABLE_WEB_SEARCH:
    _OTHER_ACTIONS.append("web_search")
if ENABLE_FETCH_URL:
    _OTHER_ACTIONS.append("fetch_webpage")
if ENABLE_MCP:
    _OTHER_ACTIONS.append("exe_mcp")

ACTIONS = f"""
{ACTIONS_BODY}

MULTI-ACTION SUPPORT:
You can output MULTIPLE actions in one cycle by using an "actions" array instead of a single "action". Example:
{{"actions": [{{"action": "explore_schema"}}, {{"action": "explore_functions"}}]}}

GROUPING RULES:
- Group 1 (Explore & Image Selection): {', '.join(_GROUP_1_ACTIONS)}. These can be batched together.
- Group 2 (User Interaction): {', '.join(_GROUP_2_ACTIONS)}. These can be batched together. summary_and_pause and attempt_completion must be the LAST action in the array, and each can appear at most once.
- Group 1 and Group 2 CANNOT be mixed in the same "actions" array. In particular, NEVER output `select_images` together with `ask_question`, `ask_choice`, `summary_and_pause`, or `attempt_completion`.
- Correct: {{"actions": [{{"action": "explore_schema"}}, {{"action": "select_images", "images": [...]}}]}}
- Correct: {{"actions": [{{"action": "ask_question", "text": "..."}}, {{"action": "ask_choice", "text": "..."}}]}}
- INVALID: {{"actions": [{{"action": "select_images", "images": [...]}}, {{"action": "ask_question", "text": "..."}}]}}
- All other actions ({', '.join(_OTHER_ACTIONS)}) must be used as single actions only.
"""

_DECISION_RULES = [
    "If the plan has an empty todo list, choose ask_question with a polite response to the user.",
    "If the plan is complete or no further actions needed, choose attempt_completion.",
    "If you need to ask the user something, choose ask_question or ask_choice.",
    "If you want to pause and show progress, choose summary_and_pause.",
    "`generate_and_execute` is the major action to solve complex problems.",
    "`explore_schema` returns all relevant data structure and schema in the database at a time based on previous context. DO NOT try to perform two explore_schema with the same consecutively.",
    "`explore_functions` returns all relevant available python function catalog at a time based on previous context. DO NOT try to perform two explore_functions with the same consecutively.",
    "When you have multiple actions that are independent and belong to the same group, use the \"actions\" array to output them together. This is more efficient than executing them one by one. For example, if you need to explore both schema and functions, output both in one cycle.",
    "`select_images` overwrites the SELECTED IMAGES region of the blackboard with images you want the LLM to keep seeing. Each image needs a local filename or an http(s) URL plus a one-sentence reason. Images generated in earlier turns of this conversation remain valid candidates even if they are no longer listed in the current IMAGES region, which only keeps the latest code execution's images; do not reject or claim an earlier generated image is gone just because it is absent from that region. Use it when generated charts or reference images are relevant to the current task; when the user's requirements change (new scope, new analysis target, or a correction), re-run it to refresh the region instead of relying on stale selections. It can be batched with explore actions.",
    "Do not call `select_images` again when the SELECTED IMAGES region already contains exactly the same image paths. Call it only when the selection actually changes.",
    "If the user asks to look at, observe, describe, or inspect an image, you MUST use `select_images` with the exact image filename in the current cycle and must NOT use `generate_and_execute` or any user-interaction action in the same cycle. Do not answer from text memory and do not claim to have viewed an image that has not been selected. When the user refers to an image by order or description, use the exact filename from the conversation; never substitute a regenerated or different image.",
    "After selecting an image for review, the next cycle should describe what you actually see in the image (layout, labels, legend, readability, issues) instead of repeating an earlier text-only analysis. Then use ask_question/ask_choice to ask for the next adjustment, or attempt_completion/summary_and_pause to finish.",
    "Regenerating an existing image is only allowed when the user explicitly asks to regenerate, modify, or improve it. A request to view, observe, or describe an existing image is NOT a regeneration request.",
    "Do not repeat an analysis that is already in the conversation. If you have already answered and are waiting for the user to choose next steps, use `ask_question` or `ask_choice`; if the task is finished, use `attempt_completion` or `summary_and_pause`. Never loop on the same action sequence.",
    "Each `explore_*` action writes/overwrites its region of the blackboard, and the blackboard is the source of truth for later code generation. When the user's requirements change (new scope, new tables, new analysis, or a correction), re-run the affected `explore_*` actions instead of relying on stale blackboard data.",
]
if ENABLE_BASE_KNOWLEDGE:
    _DECISION_RULES.append("`explore_base_knowledge` searches the business domain knowledge base with an optional keyword. Use it to retrieve relevant business rules, domain context, documentation, or thinking strategies. DO NOT perform two explore_base_knowledge consecutively.")
if ENABLE_WEB_SEARCH:
    _DECISION_RULES.append("`web_search` searches the web for real-time information. Use it when the user asks about current events, news, facts, or data that is unlikely to be in the local database.")
if ENABLE_FETCH_URL:
    _DECISION_RULES.append("`fetch_webpage` fetches and reads the full text content of a specific URL. Use it after `web_search` to get detailed information from a specific page. The URL should come from a previous search result.")
if ENABLE_MCP:
    _DECISION_RULES.append("`explore_mcp` connects to an external MCP server to discover available tools. Use it when you need capabilities not available in the local system (e.g., send emails, query external APIs, access specialized services). First `explore_mcp` to see what's available, then `exe_mcp` to call a specific tool.")
    _DECISION_RULES.append("`exe_mcp` calls a specific tool on an MCP server. Use it after `explore_mcp` has shown you the available tools. The `server` field must match the server name used in `explore_mcp`.")

DECISION_RULES_STR = "\n".join(f"{i+1}. {r}" for i, r in enumerate(_DECISION_RULES))


def _build_action_prompt(
        question: str,
        conversation_history: Optional[List[dict]],
        session_id: str = "",
) -> str:
    trimmed = prepare_trimmed_context(session_id, conversation_history)
    context = ""
    if conversation_history:
        context = history_to_text(trimmed)
    blackboard_text = blackboard_section(conversation_history)

    db_summary = get_db_summary_for_agent(engine)
    func_catalog = get_func_summary_for_agent()

    return f"""You are an action decision maker. Given the current context, decide the next action(s) to execute.

## Context:
{context if context else '(no context)'}
{blackboard_text}

## System Info
{BRIEF_INFO}

The system is working in Think → Action → Act → Observe cycles. You takes the `Action` part.


Output ONLY a valid JSON object on a single line (no md block). Choose from:

{ACTIONS}

Decision Rules:
{DECISION_RULES_STR}

"""


@perf_api("/api/action/stream/")
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
    images = blackboard_input_images_from_history(conversation_history)

    log_observe_session(session_id, question=question, status="active")

    error_msg = ""
    for i in range(2):
        if i > 0:
            yield f"data: {json.dumps({'phase': 'action', 'type': 'msg', 'content': 'Parsing failed, re-deciding next action...'}, ensure_ascii=False)}\n\n"
        else:
            yield f"data: {json.dumps({'phase': 'action', 'type': 'msg', 'content': 'Deciding next action...'}, ensure_ascii=False)}\n\n"

        raw = ""
        for chunk, reasoning in call_llm_stream_with_reasoning(prompt + error_msg, llm, images=images):
            if chunk:
                raw += chunk
                yield f"data: {json.dumps({'phase': 'action', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
            if reasoning:
                yield f"data: {json.dumps({'phase': 'action', 'type': 'reasoning_chunk', 'content': reasoning}, ensure_ascii=False)}\n\n"

        action_result = _parse_action_json(raw)
        action = action_result.get("action")
        actions = action_result.get("actions")
        if action or actions:
            yield f"data: {json.dumps({'phase': 'action', 'type': 'done', 'content': raw, 'action_result': action_result}, ensure_ascii=False)}\n\n"

            action_label = action or f"multi({len(actions)} actions)"
            log_observe_cycle(session_id, cycle_index, "action", "decide",
                              prompt=prompt[:5000], response=raw[:5000],
                              token_estimate=len(prompt) // 3)
            record_session_operation(
                session_id, "/api/action/stream/",
                request_json, str(action_result), "",
                "success", f"Decided action: {action_label}",
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
        "error", action_result.get("error", "Unknown error"),
        prompt_length=len(prompt)
    )
    error_content = action_result.get("error", "unknown")
    yield f"data: {json.dumps({'phase': 'action', 'type': 'error', 'content': f'Action failed: {error_content}'}, ensure_ascii=False)}\n\n"


def _extract_images(item: dict):
    """Read `images` without losing an explicit empty list (used to clear the region)."""
    if "images" in item:
        return item.get("images")
    return item.get("selected_images")


def _parse_action_json(raw: str) -> dict:
    result = parse_json(raw)
    if result is None:
        return {"action": None, "error": f"Failed to parse JSON: {raw.strip()[:200]}"}

    actions_list = result.get("actions")
    if actions_list is not None and isinstance(actions_list, list):
        action_names = []
        for item in actions_list:
            if not isinstance(item, dict):
                return {"action": None, "error": "Each item in the actions list must be an object", "raw": result}
            act = item.get("action", "")
            if act not in VALID_ACTIONS:
                return {"action": None, "error": f"Unknown action in actions list: {act}", "raw": result}
            action_names.append(act)
        has_group_1 = any(act in _GROUP_1_ACTIONS for act in action_names)
        has_group_2 = any(act in _GROUP_2_ACTIONS for act in action_names)
        if has_group_1 and has_group_2:
            return {
                "action": None,
                "error": "Group 1 actions (explore_*/select_images) cannot be mixed with Group 2 actions (ask_question/ask_choice/summary_and_pause/attempt_completion). Output them in separate cycles.",
                "raw": result,
            }
        return _build_multi_action_result(actions_list)

    action = result.get("action", "")
    if action not in VALID_ACTIONS:
        return {"action": None, "error": f"Unknown action: {action}", "raw": result}

    return {
        "action": action,
        "keyword": result.get("keyword"),
        "text": result.get("text"),
        "choices": result.get("choices"),
        "research_guide": result.get("research_guide"),
        "title": result.get("title"),
        "query": result.get("query"),
        "max_results": result.get("max_results"),
        "url": result.get("url"),
        "max_length": result.get("max_length"),
        "server": result.get("server"),
        "tool": result.get("tool"),
        "params": result.get("params"),
        "tools": result.get("tools"),
        "images": _extract_images(result),
    }


def _build_multi_action_result(actions_list: list) -> dict:
    return {
        "actions": [
            {
                "action": item.get("action"),
                "keyword": item.get("keyword"),
                "text": item.get("text"),
                "choices": item.get("choices"),
                "research_guide": item.get("research_guide"),
                "title": item.get("title"),
                "query": item.get("query"),
                "max_results": item.get("max_results"),
                "url": item.get("url"),
                "max_length": item.get("max_length"),
                "server": item.get("server"),
                "tool": item.get("tool"),
                "params": item.get("params"),
                "tools": item.get("tools"),
                "images": _extract_images(item),
            }
            for item in actions_list
        ],
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
