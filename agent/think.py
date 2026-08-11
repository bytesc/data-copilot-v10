import json
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.action import ACTIONS
from agent.tools.tools_def import engine, llm
from agent.tools.search_db import get_db_summary_for_agent
from agent.tools.search_func import get_func_summary_for_agent
from agent.tools.copilot.utils.call_llm_test import call_llm_stream
from data_access.session_log import record_session_operation
from data_access.observe_log import log_observe_cycle, log_observe_session

router = APIRouter()


class ThinkInput(BaseModel):
    question: str
    session_id: Optional[str] = None
    conversation_history: Optional[List[str]] = None


def _event_stream_think(
    question: str,
    session_id: str,
    conversation_history: Optional[List[str]],
):
    """Think phase: pure LLM reasoning with custom prompt to generate a plan."""
    log_observe_session(session_id, question=question, status="active")

    if conversation_history:
        context = "\n".join(conversation_history)
    else:
        context = question

    db_summary = get_db_summary_for_agent(engine)
    func_catalog = get_func_summary_for_agent()

    think_prompt = f"""You are an autonomous data analysis Thinker. Your job is to take a user's question, think about it and analyze the available database and tools, and produce a structured plan.

Database Overview:
Use `explore_schema` action to explore table schemas and sample data in detail. Then use `generate_and_execute` action to exe_sql

Some Available Functions:
{func_catalog}
Use `explore_functions` action for more available functions. Then use `generate_and_execute` action to call.

The system is working in Think → Action → Act → Observe cycles. You takes the `Think` part.

ACTIONS AVAILABLE:
{ACTIONS}

Context (includes conversation history and user questions):
{context}

Rules:
1. Each step should be a specific, actionable task.
2. The todo list should contain between 1 and 10 items. If the question is a simple greeting, chat, summary or requires no data analysis, set todo to an empty list. If all tasks are done, set todo to an empty list.
3. Mention specific table names and field names in data retrieval tasks.
4. Each step can contain ONE query AND ONE plot, OR multiple queries (any number, but no plotting).
5. When the user asks to analyze data, ALWAYS prefer querying the database directly.
6. Do NOT mention specific function or API names - describe what data to get, not how to get it.

Output ONLY a valid JSON object on a single line(no md block):

{{"description": "Brief analysis strategy in markdown...", "todo": ["Task 1", "Task 2", "Task 3"]}}

If the question requires no data analysis (greeting, clarification, etc.), output an empty todo list.
The description should be a short paragraph describing the overall approach.
The todo list contains the actionable steps. Keep task descriptions concise."""

    prompt_length = len(think_prompt)
    raw = ""

    yield f"data: {json.dumps({'phase': 'think', 'sub_phase': 'plan', 'type': 'status', 'content': '正在生成分析计划...'}, ensure_ascii=False)}\n\n"
    for chunk in call_llm_stream(think_prompt, llm):
        raw += chunk
        yield f"data: {json.dumps({'phase': 'think', 'sub_phase': 'plan', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

    plan_result = _parse_plan_json(raw)
    yield f"data: {json.dumps({'phase': 'think', 'sub_phase': 'plan', 'type': 'done', 'content': raw, 'plan_result': plan_result}, ensure_ascii=False)}\n\n"

    log_observe_cycle(session_id, 0, "think", "plan",
                      prompt=think_prompt[:5000], response=raw[:5000],
                      token_estimate=prompt_length // 3)
    record_session_operation(session_id, "/api/think/stream/", question, ans=raw, result_type="success", prompt_length=prompt_length)
    log_observe_session(session_id, status="think_done", total_cycles=0, total_tokens=prompt_length // 3)


def _parse_plan_json(raw: str) -> dict:
    raw = raw.strip()
    for prefix in ('```json', '```'):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
    for suffix in ('```',):
        if raw.endswith(suffix):
            raw = raw[:-len(suffix)]
    raw = raw.strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return {"description": raw, "todo": []}
    if not isinstance(result, dict):
        return {"description": raw, "todo": []}
    return {
        "description": result.get("description", raw),
        "todo": result.get("todo") or [],
    }


@router.post("/api/think/stream/")
async def think_stream_api(request: Request, user_input: ThinkInput):
    return StreamingResponse(
        _event_stream_think(
            user_input.question,
            user_input.session_id or "",
            user_input.conversation_history,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )