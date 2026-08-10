import json
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.tools.tools_def import engine, llm
from agent.tools.search_db import get_db_summary_for_agent
from agent.tools.search_func import get_func_summary_for_agent
from agent.tools.copilot.utils.call_llm_test import call_llm_stream
from data_access.session_log import record_session_operation
from data_access.observe_log import log_observe_cycle, log_observe_session

router = APIRouter()


class ThinkInput(BaseModel):
    question: str
    tables: Optional[List[str]] = None
    session_id: Optional[str] = None
    selected_fields: Optional[Dict[str, Any]] = None
    conversation_history: Optional[List[str]] = None


def _event_stream_think(
    question: str,
    tables: Optional[List[str]],
    session_id: str,
    selected_fields: Optional[Dict[str, Any]],
    conversation_history: Optional[List[str]],
    request_url: str,
):
    """Think phase: pure LLM reasoning with custom prompt to generate a plan."""
    log_observe_session(session_id, question=question, status="active")

    if conversation_history:
        context = "\n".join(conversation_history)
        full_question = f"Context:\n{context}\n\nCurrent Question:\n{question}"
    else:
        full_question = question

    db_summary = get_db_summary_for_agent(engine, tables)
    func_catalog = get_func_summary_for_agent()

    think_prompt = f"""You are an autonomous data analysis planner. Your job is to take a user's question, analyze the available database and tools, and produce a structured Markdown checklist of actionable steps.

Database Overview:
{db_summary}

Available Functions:
{func_catalog}

Rules:
1. Each step should be a specific, actionable task.
2. The checklist MUST contain between 1 and 10 steps (inclusive).
3. Mention specific table names and field names in data retrieval steps.
4. Each step can contain ONE query AND ONE plot, OR multiple queries (any number, but no plotting).
5. A step CANNOT contain multiple plots or multiple query+plot combinations.
6. Never mention specific function or API names - describe what data to get, not how to get it.
7. When the user asks to analyze data, ALWAYS prefer querying the database directly.
8. TABLE MATCHING RULE: Check table comments to match concepts to tables. Only ask the user if table comments are missing or ambiguous.
9. Do NOT output any code, code snippets, or conversational text. Output ONLY the Markdown checklist.
10. BEFORE generate_and_execute, you MUST first call search_db to select relevant tables and columns, and search_func to select needed functions. Never skip these steps.

After your checklist, output a line starting with NEXT_ACTION: followed by exactly one of:
- search_db (if you need to explore or search the database schema in detail)
- search_func (if you need to explore available functions in detail)
- generate_and_execute (if you are ready to execute the next step)
- output_text (if you want to display information or analysis to the user)
- ask_question (if you need to ask the user a clarifying question)
- ask_choice (if you need the user to choose from options)
- summary_and_pause (if you want to summarize progress and pause for user input)
- attempt_completion (if the entire task is complete and you want to present final results)

Question: {full_question}"""

    prompt_length = len(think_prompt)
    plan_content = ""

    yield f"data: {json.dumps({'phase': 'think', 'sub_phase': 'plan', 'type': 'status', 'content': '正在生成分析计划...'}, ensure_ascii=False)}\n\n"
    for chunk in call_llm_stream(think_prompt, llm):
        plan_content += chunk
        yield f"data: {json.dumps({'phase': 'think', 'sub_phase': 'plan', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'phase': 'think', 'sub_phase': 'plan', 'type': 'done', 'content': plan_content}, ensure_ascii=False)}\n\n"

    log_observe_cycle(session_id, 0, "think", "plan",
                      prompt=think_prompt[:5000], response=plan_content[:5000],
                      token_estimate=prompt_length // 3)
    record_session_operation(session_id, request_url, question, ans=plan_content, result_type="success", prompt_length=prompt_length)
    log_observe_session(session_id, status="think_done", total_cycles=0, total_tokens=prompt_length // 3)


@router.post("/api/think/stream/")
async def think_stream_api(request: Request, user_input: ThinkInput):
    return StreamingResponse(
        _event_stream_think(
            user_input.question,
            user_input.tables,
            user_input.session_id or "",
            user_input.selected_fields,
            user_input.conversation_history,
            request.url.path,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )