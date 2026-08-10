import json
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.tools.tools_def import llm
from agent.tools.copilot.utils.call_llm_test import call_llm_stream
from data_access.session_log import record_session_operation
from data_access.observe_log import log_observe_cycle

router = APIRouter()


class ObserveInput(BaseModel):
    question: str
    tables: Optional[List[str]] = None
    session_id: Optional[str] = None
    selected_fields: Optional[Dict[str, Any]] = None
    execution_result: Optional[str] = ""
    execution_error: Optional[str] = ""
    current_plan: Optional[str] = ""
    conversation_history: Optional[List[str]] = None
    cycle_index: int = 0
    db_context: Optional[str] = None
    func_context: Optional[str] = None


def _event_stream_observe(
    question: str,
    tables: Optional[List[str]],
    session_id: str,
    selected_fields: Optional[Dict[str, Any]],
    execution_result: str,
    execution_error: str,
    current_plan: str,
    conversation_history: Optional[List[str]],
    cycle_index: int,
    request_url: str,
    db_context: Optional[str] = None,
    func_context: Optional[str] = None,
):
    """Observe phase: LLM reviews execution results and updates the plan."""
    yield f"data: {json.dumps({'phase': 'observe', 'sub_phase': 'review', 'type': 'status', 'content': '正在审查执行结果...'}, ensure_ascii=False)}\n\n"

    if conversation_history:
        context = "\n".join(conversation_history)
    else:
        context = ""

    db_section = f"\n\nAvailable Database Context:\n{db_context}" if db_context else ""
    func_section = f"\n\nAvailable Functions:\n{func_context}" if func_context else ""

    observe_prompt = f"""You are an autonomous checklist executor. Your job is to review the execution results of the last step, update the checklist accordingly, and output ONLY the updated Markdown checklist.

Current Plan:
{current_plan or '(no plan yet)'}

Execution Result:
{execution_result[:3000] if execution_result else '(no result)'}

Execution Error:
{execution_error if execution_error else '(no error)'}
{db_section}{func_section}

Context:
{context if context else '(no context)'}

Original Question:
{question}

Autonomous State Judgment & Update Rules:
1. ANALYZE RESULT FIRST: Look at the Execution Result. Focus on the actual data returned or error traces.
2. SUCCESS: If the result contains the expected data/confirmation without errors, mark the corresponding checklist step as `- [x]`.
3. ERROR / EXCEPTION (Autonomous Correction): If the result contains error messages (e.g., KeyError, ValueError, SQL syntax error, missing parameters), DO NOT ask the user. You MUST autonomously modify the failed step to fix the error and keep it as `- [ ]`.
4. PARTIAL SUCCESS: If only part of the task was completed, mark the completed part `- [x]` and append new `- [ ]` steps for the remaining work.
5. The checklist MUST contain between 1 and 10 steps (inclusive).
6. Never mention specific function or API names - describe what data to get, not how to get it.
7. Do NOT output any code, code snippets, or conversational text. Output ONLY the updated Markdown checklist.
8. Use [x] to update multiple items if more than one is done. Never return the same list without doing anything!
9. BEFORE generate_and_execute, you MUST first call search_db to select relevant tables and columns, and search_func to select needed functions. Never skip these steps.

After your checklist, output a line starting with NEXT_ACTION: followed by exactly one of:
- search_db (if you need to explore or search the database schema in detail)
- search_func (if you need to explore available functions in detail)
- generate_and_execute (if ready to execute the next step)
- output_text (if you want to display information or analysis to the user)
- ask_question (if you need to ask the user a clarifying question)
- ask_choice (if you need the user to choose from options)
- summary_and_pause (if you want to summarize progress and pause for user input)
- attempt_completion (if the entire task is complete and you want to present final results)

Output ONLY the Markdown checklist followed by NEXT_ACTION:"""

    prompt_length = len(observe_prompt)
    plan_content = ""

    for chunk in call_llm_stream(observe_prompt, llm):
        plan_content += chunk
        yield f"data: {json.dumps({'phase': 'observe', 'sub_phase': 'review', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'phase': 'observe', 'sub_phase': 'review', 'type': 'done', 'content': plan_content}, ensure_ascii=False)}\n\n"

    log_observe_cycle(session_id, cycle_index, "observe", "review",
                      prompt=observe_prompt[:5000], response=plan_content[:5000],
                      exec_result=execution_result[:3000], exec_error=execution_error[:1000],
                      token_estimate=prompt_length // 3)
    record_session_operation(session_id, request_url, question, ans=plan_content, result_type="success", prompt_length=prompt_length)


@router.post("/api/observe/stream/")
async def observe_stream_api(request: Request, user_input: ObserveInput):
    return StreamingResponse(
        _event_stream_observe(
            user_input.question,
            user_input.tables,
            user_input.session_id or "",
            user_input.selected_fields,
            user_input.execution_result or "",
            user_input.execution_error or "",
            user_input.current_plan or "",
            user_input.conversation_history,
            user_input.cycle_index,
            request.url.path,
            user_input.db_context,
            user_input.func_context,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )