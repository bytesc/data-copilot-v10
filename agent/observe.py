import json
import traceback
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.action import ACTIONS_BRIEF
from agent.tools.base_knowledge.get_base_knowledge import TARGET
from agent.tools.tools_def import llm
from data_access.session_log import record_session_operation
from utils.front_utils import history_to_text
from utils.blackboard import blackboard_section, blackboard_input_images_from_history, last_act_action
from utils.context_trim import prepare_trimmed_context, save_session_step, parse_json_raw, parse_json, stream_with_context_retry
from utils.get_config import config_data
from utils.perf_log import perf_api

_ENABLE_BASE_KNOWLEDGE = config_data.get('enable_base_knowledge', True)
_ENABLE_TARGET = config_data.get('enable_target_knowledge', False)

router = APIRouter()


class ObserveInput(BaseModel):
    question: str
    session_id: Optional[str] = None
    conversation_history: Optional[List[dict]] = None


def _build_observe_prompt(context: str, blackboard_text: str) -> str:
    target_section = ""
    if _ENABLE_TARGET and TARGET.strip() != "":
        target_section = "The target document template below defines the content that must be included. Review the execution results against this template to determine what still needs to be done:\n\n" + TARGET

    rules = [
        "ANALYZE RESULT FIRST: Look at the context for execution results and error traces.",
        "SUCCESS: If the result contains the expected data/confirmation without errors, remove that task from the todo list.",
        "ERROR / EXCEPTION (Autonomous Correction): If the context contains error messages, DO NOT ask the user. Keep the failed task in the todo list unchanged so the next Action cycle retries it; do not rewrite or replace the step yourself — the retry loop and code generation handle the fix.",
        "PARTIAL SUCCESS: If only part of the task was completed, remove completed parts and append new tasks for remaining work.",
        "Keep completed tasks out of the todo list — only include PENDING tasks.",
    ]
    if target_section:
        rules.append(
            "CRITICAL — COMPLETENESS CHECK: Before setting todo to empty, compare what has been accomplished against the target document template above. If any section, data point, image/chart, or table from the template has not been addressed, add tasks to cover them. Do NOT mark the plan as complete if the target document template has requirements that have not been fulfilled."
        )
    rules.append("If there are pending tasks, the todo list should contain between 1 and 10 items.")
    rules.append("Your job is an objective Observer, do not be creative to new solutions.")
    rules_str = "\n".join(f"{i + 1}. {rule}" for i, rule in enumerate(rules))

    return f"""You are an objective Observer. Your job is to review the execution results of the last step and update the remaining todo list accordingly (remove completed tasks, keep pending ones). You do not rewrite task steps.

{target_section}

Context (includes execution results and errors):
{context if context else '(no context)'}
{blackboard_text}

The system is working in Think → Action → Act → Observe cycles. You takes the `Observe` part.

ACTIONS AVAILABLE (reference only — do not output action JSON):
{ACTIONS_BRIEF}

⚠️ LANGUAGE — READ THIS FIRST: Before generating any output, check the user's original question language. All the prose you write (the description and todo items) MUST be in the EXACT SAME language as the user's original question. If the user asked in Chinese, you MUST write the prose in Chinese. If the user asked in English, you MUST write the prose in English. This is NOT a suggestion — it is a HARD REQUIREMENT. The context may contain mixed languages — it is for factual content ONLY. Their language must NEVER leak into the prose you write. Table names, field names, and data values quoted from the database keep their original language and MUST NOT be translated. VIOLATING THIS RULE IS A CRITICAL ERROR.

Autonomous State Judgment & Update Rules:
{rules_str}

- `explore_schema` returns all relevant data structure and schema in the database at a time based on previous context: ALL tables are explored and only relevant ones are returned. For the SAME input it is already complete — do NOT run explore_schema again with the same input; re-run it only when the user's requirements change (new scope, tables, or analysis).
- `explore_functions` returns all relevant available python function catalog at a time based on previous context: ALL functions are explored and only relevant ones are returned. For the SAME input it is already complete — do NOT run explore_functions again with the same input; re-run it only when the user's requirements change.""" + ("""
- `explore_base_knowledge` returns all relevant business domain knowledge at a time based on previous context: ALL knowledge entries are explored and only relevant ones are returned. For the SAME input it is already complete — do NOT run explore_base_knowledge again with the same input; re-run it only when the user's requirements or domain context change.""" if _ENABLE_BASE_KNOWLEDGE else "") + """

Output ONLY a valid JSON object on a single line (no md block):
{{"description": "Brief review of what happened and updated strategy in markdown...", "todo": ["Remaining task 1", "Remaining task 2"]}}

If todo is empty, the plan is complete. Keep descriptions concise."""


@perf_api("/api/observe/stream/")
def _event_stream_observe(
    question: str,
    session_id: str,
    conversation_history: Optional[List[dict]],
    request_json: str = "",
):
    """Observe phase wrapper: turn unexpected errors into a terminal error event.

    Without this guard an unhandled exception closes the SSE stream mid-flight
    and skips the history update, so the caller sees no state change and retries
    the same phase forever. Emitting a fatal error event lets the client stop.
    """
    try:
        yield from _event_stream_observe_impl(
            question, session_id, conversation_history, request_json,
        )
    except Exception as e:
        traceback.print_exc()
        message = f"Internal error during `observe`: {e}"
        yield f"data: {json.dumps({'phase': 'observe', 'type': 'error', 'content': message, 'fatal': True}, ensure_ascii=False)}\n\n"
        try:
            record_session_operation(
                session_id, "/api/observe/stream/", request_json,
                ans="", result_type="error", msg=message[:500],
            )
        except Exception:
            traceback.print_exc()


def _event_stream_observe_impl(
    question: str,
    session_id: str,
    conversation_history: Optional[List[dict]],
    request_json: str = "",
):
    """Observe phase: LLM reviews execution results and updates the plan."""
    yield f"data: {json.dumps({'phase': 'observe', 'sub_phase': 'review', 'type': 'status', 'content': 'Reviewing execution results...'}, ensure_ascii=False)}\n\n"

    images = blackboard_input_images_from_history(conversation_history)

    def build_prompt(level):
        trimmed = prepare_trimmed_context(session_id, conversation_history, level=level)
        # No history (a direct API caller may omit it): fall back to the current
        # question instead of an empty "(no context)", matching Think/Action/Act.
        context = history_to_text(trimmed) if conversation_history else question
        blackboard_text = blackboard_section(conversation_history, level=level)
        return _build_observe_prompt(context, blackboard_text)

    observe_prompt = build_prompt(0)
    prompt_length = len(observe_prompt)
    error_msg = ""

    for i in range(2):
        if i > 0:
            yield f"data: {json.dumps({'phase': 'observe', 'sub_phase': 'review', 'type': 'msg', 'content': 'Parsing failed, re-reviewing execution results...'}, ensure_ascii=False)}\n\n"
        else:
            yield f"data: {json.dumps({'phase': 'observe', 'sub_phase': 'review', 'type': 'msg', 'content': 'Reviewing execution results...'}, ensure_ascii=False)}\n\n"

        raw = ""
        for chunk, reasoning in stream_with_context_retry(lambda lvl: build_prompt(lvl) + error_msg, llm, images=images):
            if chunk:
                raw += chunk
                yield f"data: {json.dumps({'phase': 'observe', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
            if reasoning:
                yield f"data: {json.dumps({'phase': 'observe', 'type': 'reasoning_chunk', 'content': reasoning}, ensure_ascii=False)}\n\n"

        plan_result = _parse_plan_json(raw)
        if plan_result is not None:
            yield f"data: {json.dumps({'phase': 'observe', 'type': 'done', 'content': raw, 'plan_result': plan_result}, ensure_ascii=False)}\n\n"

            record_session_operation(session_id, "/api/observe/stream/", request_json, ans=raw, result_type="success", prompt_length=prompt_length)
            observe_entry = {"role": "assistant", "type": "observe", "content": parse_json_raw(raw)}
            observe_action = last_act_action(conversation_history)
            if observe_action:
                observe_entry["action"] = observe_action
            history = save_session_step(session_id, conversation_history, [observe_entry])
            if history:
                yield f"data: {json.dumps({'type': 'history', 'history': history}, ensure_ascii=False)}\n\n"
            return

        error_msg = "\n\nPrevious attempt failed. Output ONLY a single-line JSON object with 'description' and 'todo' fields. No markdown code blocks, no extra text, no line breaks.\n"

    yield f"data: {json.dumps({'phase': 'observe', 'sub_phase': 'review', 'type': 'error', 'content': 'Failed to review after retries'}, ensure_ascii=False)}\n\n"


def _parse_plan_json(raw: str) -> dict | None:
    result = parse_json(raw)
    if isinstance(result, dict):
        return {
            "description": result.get("description", raw),
            "todo": result.get("todo") or [],
        }
    return None


@router.post("/api/observe/stream/")
async def observe_stream_api(request: Request, user_input: ObserveInput):
    return StreamingResponse(
        _event_stream_observe(
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