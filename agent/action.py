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
from agent.tools.tools_def import engine

router = APIRouter()

VALID_ACTIONS = [
    "explore_schema", "explore_functions", "generate_and_execute",
    "output_text", "ask_question", "ask_choice",
    "summary_and_pause", "attempt_completion",
]


class ActionInput(BaseModel):
    question: str
    session_id: Optional[str] = None
    conversation_history: Optional[List[str]] = None
    cycle_index: int = 0

ACTIONS="""

- explore_schema: {{"action": "explore_schema"}}
  Explore the database schema and structure based on previous context. Not used to query data, you should use `generate_and_execute` to exe_sql.
- explore_functions: {{"action": "explore_functions"}}
  Explore the available function catalog and select needed functions based on previous context.
- generate_and_execute: {{"action": "generate_and_execute", "funcs": ["exe_sql", "load_data"]}}
  Write some python code to call functions. funcs: list of function names to use. 
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
"""

def _build_action_prompt(
    question: str,
    conversation_history: Optional[List[str]],
) -> str:
    context = ""
    if conversation_history:
        context = "\n".join(conversation_history)

    db_summary = get_db_summary_for_agent(engine)
    func_catalog = get_func_summary_for_agent()

    return f"""You are an action decision maker. Given the current context, decide the SINGLE next action to execute.

Database Overview:
{db_summary}
Use `explore_schema` action to explore table schemas and sample data in detail.

Available Functions:
{func_catalog}

The system is working in Think → Action → Act → Observe cycles. You takes the `Action` part.
Context:
{context if context else '(no context)'}

Output ONLY a valid JSON object on a single line(no md code block). Choose from:

{ACTIONS}

Decision Rules:
1. If the plan has an empty todo list, choose ask_question with a polite response to the user.
2. If the plan is complete or no further actions needed, choose attempt_completion.
3. If you need to ask the user something, choose ask_question or ask_choice.
4. If you want to pause and show progress, choose summary_and_pause.
5. `generate_and_execute` is the major action to solve complex problems.
6. `explore_schema` returns all relevant data structure and schema in the database at a time based on previous context. DO NOT try to perform two explore_schema with the same consecutively.
7. `explore_functions` returns all relevant available python function catalog at a time based on previous context. DO NOT try to perform two explore_functions with the same consecutively.

"""


def _event_stream_action(
    question: str,
    session_id: str,
    conversation_history: Optional[List[str]],
    cycle_index: int,
):
    yield f"data: {json.dumps({'phase': 'action', 'type': 'status', 'content': '正在决策下一步动作...'}, ensure_ascii=False)}\n\n"

    prompt = _build_action_prompt(
        question, conversation_history,
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
            user_input.session_id or "",
            user_input.conversation_history,
            user_input.cycle_index,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )