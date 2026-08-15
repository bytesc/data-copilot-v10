import json
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.action import ACTIONS
from agent.tools.tools_def import llm
from agent.tools.copilot.utils.call_llm_test import call_llm_stream
from data_access.session_log import record_session_operation
from data_access.observe_log import log_observe_cycle
from utils.front_utils import history_to_text
from utils.context_trim import prepare_trimmed_context, save_session_step

router = APIRouter()


class ObserveInput(BaseModel):
    question: str
    session_id: Optional[str] = None
    conversation_history: Optional[List[dict]] = None
    cycle_index: int = 0


def _event_stream_observe(
    question: str,
    session_id: str,
    conversation_history: Optional[List[dict]],
    cycle_index: int,
    request_json: str = "",
):
    """Observe phase: LLM reviews execution results and updates the plan."""
    yield f"data: {json.dumps({'phase': 'observe', 'sub_phase': 'review', 'type': 'status', 'content': '正在审查执行结果...'}, ensure_ascii=False)}\n\n"

    trimmed = prepare_trimmed_context(session_id, conversation_history)
    if conversation_history:
        context = history_to_text(trimmed)
    else:
        context = ""

    observe_prompt = f"""You are an objective Observer. Your job is to review the execution results of the last step, update the plan accordingly.

The system is working in Think → Action → Act → Observe cycles. You takes the `Observe` part.

ACTIONS AVAILABLE:
{ACTIONS}

Context (includes execution results and errors):
{context if context else '(no context)'}

Autonomous State Judgment & Update Rules:
1. ANALYZE RESULT FIRST: Look at the context for execution results and error traces.
2. SUCCESS: If the result contains the expected data/confirmation without errors, remove that task from the todo list.
3. ERROR / EXCEPTION (Autonomous Correction): If the context contains error messages, DO NOT ask the user. Keep the failed task in the todo list. Do not modify steps to fix the error.
4. PARTIAL SUCCESS: If only part of the task was completed, remove completed parts and append new tasks for remaining work.
5. Keep completed tasks out of the todo list — only include PENDING tasks.
6. If all tasks are done, set todo to an empty list.
7. If there are pending tasks, the todo list should contain between 1 and 10 items.
8. Your job is an objective Observer, do not be creative to new solutions.

- `explore_schema` returns all relevant data structure and schema in the database at a time based on previous context. ALL tables are explored and only return relevant ones! explored means completed! NO need to perform explore_schema with the same input again!
- `explore_functions` returns all relevant available python function catalog at a time based on previous context. ALL functions are explored and only return relevant ones! explored means completed! NO need to perform explore_functions with the same input again!

Output ONLY a valid JSON object on a single line:
{{"description": "Brief review of what happened and updated strategy in markdown...", "todo": ["Remaining task 1", "Remaining task 2"]}}

If todo is empty, the plan is complete. Keep descriptions concise."""

    prompt_length = len(observe_prompt)
    raw = ""

    for chunk in call_llm_stream(observe_prompt, llm):
        raw += chunk
        yield f"data: {json.dumps({'phase': 'observe',  'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

    plan_result = _parse_plan_json(raw)
    yield f"data: {json.dumps({'phase': 'observe', 'type': 'done', 'content': raw, 'plan_result': plan_result}, ensure_ascii=False)}\n\n"

    log_observe_cycle(session_id, cycle_index, "observe", "review",
                      prompt=observe_prompt[:5000], response=raw[:5000],
                      token_estimate=prompt_length // 3)
    record_session_operation(session_id, "/api/observe/stream/", request_json, ans=raw, result_type="success", prompt_length=prompt_length)
    save_session_step(session_id, conversation_history, [{"role": "assistant", "type": "observe", "action": "", "content": raw}])


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


@router.post("/api/observe/stream/")
async def observe_stream_api(request: Request, user_input: ObserveInput):
    return StreamingResponse(
        _event_stream_observe(
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