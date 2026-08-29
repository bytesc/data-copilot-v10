import json
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.action import ACTIONS
from agent.tools.base_knowledge.get_base_knowledge import DB_BRIEF, BASE, TARGET
from agent.tools.tools_def import engine, llm
from agent.tools.search_db import get_db_summary_for_agent
from agent.tools.search_func import get_func_summary_for_agent
from agent.tools.copilot.utils.call_llm_test import call_llm_stream
from data_access.session_log import record_session_operation
from data_access.observe_log import log_observe_cycle, log_observe_session
from utils.front_utils import history_to_text
from utils.context_trim import prepare_trimmed_context, save_session_step, parse_json_raw, parse_json

router = APIRouter()


class ThinkInput(BaseModel):
    question: str
    session_id: Optional[str] = None
    conversation_history: Optional[List[dict]] = None


def _event_stream_think(
    question: str,
    session_id: str,
    conversation_history: Optional[List[dict]],
    request_json: str = "",
):
    """Think phase: pure LLM reasoning with custom prompt to generate a plan."""
    log_observe_session(session_id, question=question, status="active")

    trimmed = prepare_trimmed_context(session_id, conversation_history)
    if conversation_history:
        context = history_to_text(trimmed)
    else:
        context = question

    db_summary = get_db_summary_for_agent(engine)
    func_catalog = get_func_summary_for_agent()
    base_knowledge = BASE

    target_section = ""
    if TARGET.strip() != "":
        target_section = "The target document template below defines the final report structure and content that must be produced. Ensure your plan covers all sections, data points, images, and tables required by this template:\n\n" + TARGET

    think_prompt = f"""You are an autonomous data analysis Thinker. Your job is to take a user's question, think about it and analyze the available database and tools, and produce a structured plan.

{base_knowledge}

{target_section}

Database Information:
{DB_BRIEF}
Use `explore_schema` action to explore table schemas and sample data in detail. Then use `generate_and_execute` action to exe_sql

Some Available Functions:
{func_catalog}
Use `explore_functions` action for more available functions. Then use `generate_and_execute` action to call.

The system is working in Think → Action → Act → Observe cycles. You takes the `Think` part.

ACTIONS AVAILABLE:
{ACTIONS}

Context (includes conversation history and user questions):
{context}

⚠️ LANGUAGE — READ THIS FIRST: Before generating any output, check the user's question language. Your ENTIRE output (description and todo items) MUST be in the EXACT SAME language as the user's question. If the user asked in Chinese, you MUST write in Chinese. If the user asked in English, you MUST write in English. This is NOT a suggestion — it is a HARD REQUIREMENT. The context, database information, and knowledge base may contain mixed languages — they are for factual content ONLY. Their language must NEVER leak into your output. Every word you output must be in the user's language. VIOLATING THIS RULE IS A CRITICAL ERROR.

Rules:
1. Each step should be a specific, actionable task.
2. The todo list should contain between 1 and 10 items. If the question is a simple greeting, chat, summary or requires no data analysis, set todo to an empty list. If all tasks are done, set todo to an empty list.
3. Mention specific table names and field names in data retrieval tasks.
4. Each step can contain ONE query AND ONE plot, OR multiple queries (any number, but no plotting).
5. When the user asks to analyze data, ALWAYS prefer querying the database directly.
6. Do NOT mention specific function or API names - describe what data to get, not how to get it.
7. CRITICAL — VISUALIZATION REQUIREMENT: Whenever the todo list includes any data retrieval or analysis task, you MUST also include a follow-up task that generates a chart or visualization of that data. The chart task should be a separate todo item placed immediately after its corresponding data task. For example: ["Query sales data from the database", "Create a bar chart showing sales by category"]. Do NOT skip visualization unless the user explicitly asks for text-only output.

Output ONLY a valid JSON object on a single line (no md block):

{{"description": "Brief analysis strategy in markdown...", "todo": ["Task 1", "Task 2", "Task 3"]}}

If the question requires no data analysis (greeting, clarification, etc.), output an empty todo list.
The description should be a short paragraph describing the overall approach.
The todo list contains the actionable steps. Keep task descriptions concise.

⚠️ FINAL LANGUAGE CHECK: The knowledge base above is in Chinese — IGNORE THAT. Your output MUST be in the user's language. Check the user's question now: what language is it in? Write your ENTIRE response in that language. Do NOT copy the knowledge base's language."""

    prompt_length = len(think_prompt)
    error_msg = ""

    for i in range(2):
        if i > 0:
            yield f"data: {json.dumps({'phase': 'think', 'type': 'msg', 'content': '解析失败，正在重新生成分析计划...'}, ensure_ascii=False)}\n\n"
        else:
            yield f"data: {json.dumps({'phase': 'think', 'type': 'msg', 'content': '正在生成分析计划...'}, ensure_ascii=False)}\n\n"

        raw = ""
        for chunk in call_llm_stream(think_prompt + error_msg, llm):
            raw += chunk
            yield f"data: {json.dumps({'phase': 'think', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

        plan_result = _parse_plan_json(raw)
        if plan_result is not None:
            yield f"data: {json.dumps({'phase': 'think', 'type': 'done', 'content': raw, 'plan_result': plan_result}, ensure_ascii=False)}\n\n"

            log_observe_cycle(session_id, 0, "think", "plan",
                              prompt=think_prompt[:5000], response=raw[:5000],
                              token_estimate=prompt_length // 3)
            record_session_operation(session_id, "/api/think/stream/", request_json, ans=raw, result_type="success", prompt_length=prompt_length)
            log_observe_session(session_id, status="think_done", total_tokens=prompt_length // 3)
            history = save_session_step(session_id, conversation_history, [{"role": "assistant", "type": "think", "content": parse_json_raw(raw)}])
            if history:
                yield f"data: {json.dumps({'type': 'history', 'history': history}, ensure_ascii=False)}\n\n"
            return

        error_msg = "\n\nPrevious attempt failed. Output ONLY a single-line JSON object with 'description' and 'todo' fields. No markdown code blocks, no extra text, no line breaks.\n"

    yield f"data: {json.dumps({'phase': 'think', 'type': 'error', 'content': 'Failed to generate plan after retries'}, ensure_ascii=False)}\n\n"


def _parse_plan_json(raw: str) -> dict | None:
    result = parse_json(raw)
    if isinstance(result, dict):
        return {
            "description": result.get("description", raw),
            "todo": result.get("todo") or [],
        }
    return None


@router.post("/api/think/stream/")
async def think_stream_api(request: Request, user_input: ThinkInput):
    return StreamingResponse(
        _event_stream_think(
            user_input.question,
            user_input.session_id or "",
            user_input.conversation_history,
            user_input.model_dump_json(),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )