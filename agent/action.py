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
    "search_db", "search_func", "generate_and_execute",
    "output_text", "ask_question", "ask_choice",
    "summary_and_pause", "attempt_completion",
]


class ActionInput(BaseModel):
    question: str
    tables: Optional[List[str]] = None
    session_id: Optional[str] = None
    conversation_history: Optional[List[str]] = None
    current_plan: Optional[str] = ""
    db_context: Optional[str] = None
    func_context: Optional[str] = None
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
    db_context: Optional[str],
    func_context: Optional[str],
    conversation_history: Optional[List[str]],
) -> str:
    context = ""
    if conversation_history:
        context = "\n".join(conversation_history)

    db_section = f"\n\nDatabase Context:\n{db_context}" if db_context else ""
    func_section = f"\n\nAvailable Functions:\n{func_context}" if func_context else ""

    return f"""You are an action decision maker. Given the current context, decide the SINGLE next action to execute.

Current Plan:
{_extract_plan_text(current_plan)}
{db_section}{func_section}

Context:
{context if context else '(no context)'}

Question:
{question}

Output ONLY a valid JSON object on a single line. Choose from:

- search_db: {{"action": "search_db", "keyword": "optional multi-word keyword"}}
  Only include keyword if you want to narrow the search. Multiple keywords can be space-separated.
- search_func: {{"action": "search_func", "keyword": "optional keyword"}}
- generate_and_execute: {{"action": "generate_and_execute", "funcs": ["exe_sql", "load_data"]}}
  funcs: optional list of function names to use. Omit if not needed.
- output_text: {{"action": "output_text", "text": "Your response content here..."}}
- ask_question: {{"action": "ask_question", "text": "Your question for the user here..."}}
- ask_choice: {{"action": "ask_choice", "text": "Your question here...", "choices": ["option1", "option2"]}}
- summary_and_pause: {{"action": "summary_and_pause", "text": "Your progress summary here..."}}
- attempt_completion: {{"action": "attempt_completion", "text": "Your final results here..."}}

Decision Rules:
1. If the plan has an empty todo list, choose ask_question with a polite response to the user.
2. If the context shows no database search has been done, choose search_db. Provide keyword based on the question.
3. If the context shows no function search has been done, choose search_func. Provide keyword based on the question.
4. If Database Context shows "No tables or columns found matching keyword", retry search_db WITHOUT keyword.
5. If both database and functions are ready, choose generate_and_execute.
6. If the plan is complete or no further actions needed, choose attempt_completion.
7. If you need to ask the user something, choose ask_question or ask_choice.
8. If you want to pause and show progress, choose summary_and_pause.

JSON:"""


def _event_stream_action(
    question: str,
    tables: Optional[List[str]],
    session_id: str,
    conversation_history: Optional[List[str]],
    current_plan: str,
    db_context: Optional[str],
    func_context: Optional[str],
    cycle_index: int,
    request_url: str,
):
    yield f"data: {json.dumps({'phase': 'action', 'type': 'status', 'content': '正在决策下一步动作...'}, ensure_ascii=False)}\n\n"

    prompt = _build_action_prompt(
        question, current_plan,
        db_context, func_context, conversation_history,
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
            user_input.db_context,
            user_input.func_context,
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