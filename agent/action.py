import json
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.tools.tools_def import llm
from agent.tools.copilot.utils.call_llm_test import call_llm_stream
from data_access.observe_log import log_observe_cycle

router = APIRouter()

VALID_ACTIONS = [
    "explore_schema", "explore_functions", "generate_and_execute",
    "output_text", "ask_question", "ask_choice",
    "summary_and_pause", "attempt_completion",
]


class ActionInput(BaseModel):
    question: str
    tables: Optional[List[str]] = None
    session_id: Optional[str] = None
    conversation_history: Optional[List[str]] = None
    current_plan: Optional[str] = ""
    cycle_index: int = 0


def _extract_plan_text(current_plan: str) -> str:
    try:
        plan = json.loads(current_plan)
        if isinstance(plan, dict):
            desc = plan.get("description", "")
            todo = plan.get("todo") or []
            lines = [desc] if desc else []
            if todo:
                lines.append("")
                lines.append("Pending Tasks:")
                for t in todo:
                    lines.append(f"- [ ] {t}")
            return "\n".join(lines)
    except (json.JSONDecodeError, TypeError):
        pass
    return current_plan or "(no plan yet)"


def _build_action_prompt(
    question: str,
    current_plan: str,
    conversation_history: Optional[List[str]],
) -> str:
    context = ""
    if conversation_history:
        context = "\n".join(conversation_history)

    return f"""You are an action decision maker. Given the current context, decide the SINGLE next action to execute.

Current Plan:
{_extract_plan_text(current_plan)}

Context:
{context if context else '(no context)'}

Output ONLY a valid JSON object on a single line. Choose from:

- explore_schema: {{"action": "explore_schema", "keyword": "optional keyword"}}
  Explore the database schema to select relevant tables and columns. Only include keyword to narrow the scope.
- explore_functions: {{"action": "explore_functions", "keyword": "optional keyword"}}
  Explore the available function catalog to select needed functions.
- generate_and_execute: {{"action": "generate_and_execute", "funcs": ["exe_sql", "load_data"]}}
  funcs: optional list of function names to use. Omit if not needed.
- output_text: {{"action": "output_text", "text": "Your response content here..."}}
- ask_question: {{"action": "ask_question", "text": "Your question for the user here..."}}
- ask_choice: {{"action": "ask_choice", "text": "Your question here...", "choices": ["option1", "option2"]}}
- summary_and_pause: {{"action": "summary_and_pause", "text": "Your progress summary here..."}}
- attempt_completion: {{"action": "attempt_completion", "text": "Your final results here..."}}

Decision Rules:
1. If the plan has an empty todo list, choose ask_question with a polite response to the user.
2. EXPLORATION STRATEGY — STRICT 2-ATTEMPT LIMIT:
   Count "Selected Fields" entries in the Context. Count "Selected Functions" entries.
   a. 0 "Selected Fields" entries → call explore_schema WITH a keyword based on the question.
   b. 1 "Selected Fields" entry → call explore_schema WITHOUT keyword (omit "keyword" field entirely) to do a full search. This is the LAST schema attempt.
   c. 2 "Selected Fields" entries → STOP. NEVER call explore_schema again. Move to explore_functions, generate_and_execute, or ask_question.
   d. Same rule for explore_functions: max 2 attempts, then STOP.
3. If both schema and function exploration results exist in context, choose generate_and_execute.
4. If the plan is complete or no further actions needed, choose attempt_completion.
5. If you need to ask the user something, choose ask_question or ask_choice.
6. If you want to pause and show progress, choose summary_and_pause.

JSON:"""


def _event_stream_action(
    question: str,
    tables: Optional[List[str]],
    session_id: str,
    conversation_history: Optional[List[str]],
    current_plan: str,
    cycle_index: int,
    request_url: str,
):
    yield f"data: {json.dumps({'phase': 'action', 'type': 'status', 'content': '正在决策下一步动作...'}, ensure_ascii=False)}\n\n"

    prompt = _build_action_prompt(
        question, current_plan, conversation_history,
    )

    raw = ""
    for chunk in call_llm_stream(prompt, llm):
        raw += chunk
        yield f"data: {json.dumps({'phase': 'action', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

    action_result = _parse_action_json(raw)
    yield f"data: {json.dumps({'phase': 'action', 'type': 'done', 'content': raw, 'action_result': action_result}, ensure_ascii=False)}\n\n"

    log_observe_cycle(session_id, cycle_index, "action", "decide",
                      prompt=prompt[:5000], response=raw[:5000],
                      token_estimate=len(prompt) // 3)


def _parse_action_json(raw: str) -> dict:
    raw = raw.strip()
    for start in ('```json', '```'):
        if raw.startswith(start):
            raw = raw[len(start):]
            break
    for end in ('```',):
        if raw.endswith(end):
            raw = raw[:-len(end)]
    raw = raw.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return {"action": None, "error": f"Failed to parse JSON: {raw[:200]}"}

    action = result.get("action", "")
    if action not in VALID_ACTIONS:
        return {"action": None, "error": f"Unknown action: {action}", "raw": result}

    return {
        "action": action,
        "keyword": result.get("keyword"),
        "funcs": result.get("funcs"),
        "text": result.get("text"),
        "choices": result.get("choices"),
    }


@router.post("/api/action/stream/")
async def action_stream_api(request: Request, user_input: ActionInput):
    return StreamingResponse(
        _event_stream_action(
            user_input.question,
            user_input.tables,
            user_input.session_id or "",
            user_input.conversation_history,
            user_input.current_plan or "",
            user_input.cycle_index,
            request.url.path,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )