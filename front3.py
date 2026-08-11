import json
import re
import random
import string
import time
import traceback
from datetime import datetime
from typing import Optional, List, Dict, Any
import httpx

from pywebio.input import input, TEXT, textarea, file_upload, radio
from pywebio.output import (
    put_text, put_html, put_markdown, put_loading, toast,
    put_buttons, put_collapse, put_table,
    use_scope, put_scope, put_warning, put_info, put_success
)
from pywebio import start_server

from data_access.read_db import get_rows_from_all_tables, get_table_comments_dict, get_all_comments_from_table
from utils.front_utils import (
    upload_csv_api, upload_doc_api,
)
from utils.get_config import config_data

SERVER_URL = f"http://127.0.0.1:{config_data['server_port']}"

SELECT_TABLES = []
SELECT_LABELS = []

CURSOR = '<span class="blink-cursor">|</span> <span class="thinking-text">Thinking...</span>'
CURSOR_CSS = '''
<style>
.blink-cursor { animation: blink 1s step-end infinite; font-weight: bold; }
@keyframes blink { 50% { opacity: 0; } }
.phase-header { border-left: 4px solid #4a90d9; padding-left: 12px; margin: 16px 0 8px 0; }
.phase-think { border-left-color: #f0ad4e; }
.phase-act { border-left-color: #5cb85c; }
.phase-observe { border-left-color: #5bc0de; }
.phase-user { border-left-color: #d9534f; }
</style>
'''

ACTIONS = {
    "search_db": "search_db",
    "search_func": "search_func",
    "generate_and_execute": "generate_and_execute",
    "output_text": "output_text",
    "ask_question": "ask_question",
    "ask_choice": "ask_choice",
    "summary_and_pause": "summary_and_pause",
    "attempt_completion": "attempt_completion",
}

FRONTEND_ACTIONS = {"output_text", "ask_question", "ask_choice", "summary_and_pause", "attempt_completion"}


def _sse_stream(url: str, payload: dict):
    with httpx.stream("POST", url, json=payload, timeout=300.0) as response:
        if response.status_code != 200:
            yield {"type": "error", "content": f"HTTP {response.status_code}"}
            return
        buffer = ""
        for chunk in response.iter_text():
            buffer += chunk
            while "\n\n" in buffer:
                event_str, buffer = buffer.split("\n\n", 1)
                for line in event_str.split("\n"):
                    if line.startswith("data: "):
                        try:
                            yield json.loads(line[6:])
                        except json.JSONDecodeError:
                            pass


def think_api_stream(
    question: str,
    tables: Optional[List[str]] = None,
    conversation_history: Optional[List[str]] = None,
    session_id: str = "",
):
    payload = {"question": question, "session_id": session_id}
    if tables:
        payload["tables"] = tables
    if conversation_history:
        payload["conversation_history"] = conversation_history
    yield from _sse_stream(f"{SERVER_URL}/api/think/stream/", payload)


def act_api_stream(
    action: str,
    question: str,
    tables: Optional[List[str]] = None,
    selected_fields: Optional[dict] = None,
    selected_functions: Optional[List[str]] = None,
    conversation_history: Optional[List[str]] = None,
    session_id: str = "",
    params: Optional[dict] = None,
):
    payload = {"question": question, "action": action, "session_id": session_id}
    if tables:
        payload["tables"] = tables
    if selected_fields is not None:
        payload["selected_fields"] = selected_fields
    if selected_functions is not None:
        payload["selected_functions"] = selected_functions
    if conversation_history:
        payload["conversation_history"] = conversation_history
    if params:
        payload["params"] = params
    yield from _sse_stream(f"{SERVER_URL}/api/act/stream/", payload)


def observe_api_stream(
    question: str,
    tables: Optional[List[str]] = None,
    current_plan: str = "",
    conversation_history: Optional[List[str]] = None,
    cycle_index: int = 0,
    session_id: str = "",
    db_context: Optional[str] = None,
    func_context: Optional[str] = None,
):
    payload = {
        "question": question,
        "session_id": session_id,
        "current_plan": current_plan,
        "cycle_index": cycle_index,
    }
    if tables:
        payload["tables"] = tables
    if conversation_history:
        payload["conversation_history"] = conversation_history
    if db_context:
        payload["db_context"] = db_context
    if func_context:
        payload["func_context"] = func_context
    yield from _sse_stream(f"{SERVER_URL}/api/observe/stream/", payload)


def action_api_stream(
    question: str,
    tables: Optional[List[str]] = None,
    selected_fields: Optional[dict] = None,
    selected_functions: Optional[List[str]] = None,
    conversation_history: Optional[List[str]] = None,
    current_plan: str = "",
    db_context: Optional[str] = None,
    func_context: Optional[str] = None,
    cycle_index: int = 0,
    session_id: str = "",
):
    payload = {
        "question": question,
        "session_id": session_id,
        "current_plan": current_plan,
        "cycle_index": cycle_index,
    }
    if tables:
        payload["tables"] = tables
    if selected_fields is not None:
        payload["selected_fields"] = selected_fields
    if selected_functions is not None:
        payload["selected_functions"] = selected_functions
    if conversation_history:
        payload["conversation_history"] = conversation_history
    if db_context:
        payload["db_context"] = db_context
    if func_context:
        payload["func_context"] = func_context
    yield from _sse_stream(f"{SERVER_URL}/api/action/stream/", payload)


def parse_action_result(events: list) -> dict:
    for event in events:
        if event.get("type") == "done" and event.get("action_result"):
            return event["action_result"]
    return {"action": None, "error": "No action result"}


def run_action_phase(cycle_index, question, conversation_history, current_plan, db_context, func_context, session_id):
    try:
        phase_header("act", f"ACTION - Decide (Cycle {cycle_index})")
        action_scope = f"action_{cycle_index}"
        put_scope(action_scope)
        append_action = display_streaming(action_scope, collapse_title="Decision")

        action_events = []
        for event in action_api_stream(
            question, SELECT_TABLES,
            conversation_history=conversation_history,
            current_plan=current_plan,
            db_context=db_context,
            func_context=func_context,
            cycle_index=cycle_index,
            session_id=session_id,
        ):
            action_events.append(event)
            etype = event.get("type", "")
            append_action({"type": etype, "content": event.get("content", "")})

        return parse_action_result(action_events)
    except Exception as e:
        print(f"[ERROR] run_action_phase: cycle={cycle_index}")
        traceback.print_exc()
        raise


def display_streaming(scope_name: str, collapse_title: str = None):
    accumulated = ""
    handled = False
    last_update = 0

    put_loading(shape="grow", color="primary", scope=scope_name)

    def append_chunk(event):
        nonlocal accumulated, handled, last_update
        event_type = event.get("type")
        if event_type == "status":
            if event.get("content"):
                toast(event["content"], color='info')
        elif event_type in ("chunk", "code_chunk"):
            accumulated += event["content"]
            now = time.time()
            if now - last_update > 0.3:
                last_update = now
                with use_scope(scope_name, clear=True):
                    put_markdown(accumulated, sanitize=False)
                    put_html(CURSOR)
        elif event_type == "code_complete":
            handled = True
            accumulated = "```python\n" + event["content"] + "\n```"
            with use_scope(scope_name, clear=True):
                put_collapse("Generated Code", [
                    put_markdown(accumulated, sanitize=False)
                ], open=False)
        elif event_type == "solved":
            handled = True
            accumulated = event["content"]
            with use_scope(scope_name, clear=True):
                put_markdown(accumulated, sanitize=False)
        elif event_type == "done":
            if handled:
                return accumulated
            done_content = event.get("content", "")
            if not accumulated and done_content:
                accumulated = done_content
            with use_scope(scope_name, clear=True):
                if collapse_title and accumulated:
                    put_collapse(collapse_title, [
                        put_markdown(accumulated, sanitize=False)
                    ], open=False)
                elif accumulated:
                    put_markdown(accumulated, sanitize=False)
        elif event_type == "error":
            toast(event["content"], color='error')
            accumulated = ""
            with use_scope(scope_name, clear=True):
                put_warning(f"**Error:** {event['content']}")
        return accumulated

    return append_chunk


def phase_header(phase: str, title: str):
    css_class = f"phase-{phase}" if phase in ("think", "act", "observe", "user") else ""
    put_markdown(f'<div class="phase-header {css_class}">### {title}</div>', sanitize=False)


def _parse_plan_json(raw: str) -> dict:
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return {
                "description": result.get("description", raw),
                "todo": result.get("todo") or [],
            }
    except (json.JSONDecodeError, TypeError):
        pass
    return {"description": raw, "todo": []}


def _format_plan_display(plan: dict) -> str:
    lines = [plan.get("description", "")]
    todo = plan.get("todo") or []
    if todo:
        lines.append("\n**Pending Tasks:**")
        for t in todo:
            lines.append(f"- [ ] {t}")
    return "\n".join(lines)


def parse_think_result(events: list) -> dict:
    for event in events:
        if event.get("sub_phase") == "plan" and event.get("type") == "done":
            plan_result = event.get("plan_result")
            if plan_result:
                return plan_result
            raw = event.get("content", "")
            return _parse_plan_json(raw)
    return {"description": "", "todo": []}


def parse_observe_result(events: list) -> dict:
    for event in events:
        if event.get("sub_phase") == "review" and event.get("type") == "done":
            plan_result = event.get("plan_result")
            if plan_result:
                return plan_result
            raw = event.get("content", "")
            return _parse_plan_json(raw)
    return {"description": "", "todo": []}


def check_plan_complete(plan: dict) -> bool:
    if not plan:
        return True
    todo = plan.get("todo")
    if todo is None:
        return True
    return len(todo) == 0


def parse_act_result(events: list) -> dict:
    parsed = {
        "selected_fields": None,
        "selected_functions": None,
        "function_solved": False,
        "full_code": "",
        "full_ans": "",
        "exec_error": None,
        "solved_ans": "",
        "needs_user_input": False,
        "choices": [],
        "paused": False,
        "completed": False,
        "db_context": None,
        "func_context": None,
        "search_result": None,
    }
    for event in events:
        sub = event.get("sub_phase", "")
        etype = event.get("type", "")
        content = event.get("content", "")
        result = event.get("result")

        if etype == "done" and result and isinstance(result, dict):
            if sub in ("search_db", "search_func"):
                parsed["search_result"] = content
                parsed["db_context"] = result.get("db_context") or parsed["db_context"]
                parsed["func_context"] = result.get("func_context") or parsed["func_context"]
                if result.get("selected_fields") is not None:
                    parsed["selected_fields"] = result["selected_fields"]
                if result.get("selected_functions") is not None:
                    parsed["selected_functions"] = result["selected_functions"]
            elif sub in ("output_text", "summary", "completion"):
                parsed["full_ans"] = result.get("text", content)
                if result.get("paused"):
                    parsed["paused"] = True
                if result.get("completed"):
                    parsed["completed"] = True
            elif sub == "exec":
                parsed["full_code"] = result.get("code", "")
                parsed["full_ans"] = result.get("exec_result", "")
                parsed["exec_error"] = result.get("error")
                if result.get("solved_ans"):
                    parsed["solved_ans"] = result["solved_ans"]
            elif sub == "ask_question":
                parsed["full_ans"] = result.get("text", content)
                if result.get("needs_user_input"):
                    parsed["needs_user_input"] = True
            elif sub == "ask_choice":
                parsed["full_ans"] = result.get("text", content)
                parsed["choices"] = result.get("choices", [])
                if result.get("needs_user_input"):
                    parsed["needs_user_input"] = True
        elif etype in ("chunk", "code_chunk"):
            if sub in ("output_text", "summary", "completion"):
                parsed["full_ans"] += content
            if sub == "exec":
                parsed["full_ans"] += content
        elif sub == "code" and etype == "code_complete":
            parsed["full_code"] = content
        elif sub == "code" and etype == "solved":
            parsed["solved_ans"] = content
            parsed["function_solved"] = True
        elif sub == "exec" and etype == "error":
            parsed["exec_error"] = content

    return parsed


def handle_csv_upload():
    file_info = file_upload(
        "Please select a CSV file to upload",
        accept=".csv",
        help_text="Select the CSV file you want to upload"
    )
    if not file_info:
        return
    table_name = input("Enter table name (optional, default is 'uploaded_data')",
                       type=TEXT, placeholder="uploaded_data", required=False)
    if not table_name:
        table_name = "uploaded_data"
    with put_loading(shape="grow", color="primary"):
        result = upload_csv_api(file_info['content'], table_name)
    if result.get('type') == "error" or result.get('error'):
        toast(f"Upload failed: {result}", color='error')
    else:
        toast("File uploaded successfully!", color='success')
        put_markdown("### Upload Results")
        put_markdown(f"Table name: `{result.get('table_name', table_name)}`")
        put_markdown(f"Row count: {result.get('row_count', 'N/A')}")


def handle_doc_upload():
    file_info = file_upload(
        "Please select a document file to upload (txt, doc, docx, pdf)",
        accept=".txt,.doc,.docx,.pdf",
        help_text="Select the document file you want to upload"
    )
    if not file_info:
        return
    table_name = input("Enter table name (optional, default is 'uploaded_data')",
                       type=TEXT, placeholder="uploaded_data", required=False)
    if not table_name:
        table_name = "uploaded_data"
    with put_loading(shape="grow", color="primary"):
        result = upload_doc_api(file_info['content'], file_info['filename'], table_name)
    if result.get('error'):
        toast(f"Upload failed: {result.get('error')}", color='error')
    else:
        toast("File uploaded successfully!", color='success')
        put_markdown("### Upload Results")
        put_markdown(f"Table name: `{result.get('table_name', table_name)}`")
        put_markdown(f"Preview: {result.get('preview', 'N/A')}")


def show_db_overview():
    put_markdown("### Data View")
    with put_collapse("Tables Overview"):
        all_comments = get_all_comments_from_table()
        first_five_rows = get_rows_from_all_tables()
        for table_name, rows in first_five_rows.items():
            with put_collapse(f" table {table_name}"):
                if table_name in all_comments:
                    table_comment = all_comments[table_name].get('table_comment', '')
                    if table_comment:
                        put_text(f"{table_comment}")
                    columns = all_comments[table_name].get('columns', {})
                    if columns:
                        comment_table = [["Column Name", "Comment"]]
                        for col_name, comment in columns.items():
                            comment_table.append([col_name, comment])
                        put_table(comment_table)
                put_text(f"table {table_name} first 5 rows:")
                put_table([rows.columns.tolist()] + rows.values.tolist())


def run_think_phase(cycle_index, question, conversation_history, session_id):
    try:
        label = f"THINK - Planning" if cycle_index == 0 else f"THINK - Planning (Cycle {cycle_index})"
        phase_header("think", label)
        think_scope = f"think_{cycle_index}"
        put_scope(think_scope)
        append_think = display_streaming(think_scope, collapse_title="Plan")

        think_events = []
        for event in think_api_stream(
            question, SELECT_TABLES,
            conversation_history=conversation_history,
            session_id=session_id,
        ):
            think_events.append(event)
            sub = event.get("sub_phase", "")
            etype = event.get("type", "")
            content = event.get("content", "")
            if sub == "plan":
                append_think({"type": etype, "content": content})

        result = parse_think_result(think_events)
        with use_scope(think_scope, clear=True):
            put_collapse("Plan", [
                put_markdown(_format_plan_display(result), sanitize=False)
            ], open=False)
        return result
    except Exception as e:
        print(f"[ERROR] run_think_phase: cycle={cycle_index}")
        traceback.print_exc()
        raise


def handle_frontend_action(cycle_index, action, action_result):
    try:
        text = action_result.get("text") or ""
        choices = action_result.get("choices") or []

        phase_header("act", f"ACT - {action} (Cycle {cycle_index})")
        act_scope = f"act_{cycle_index}"
        put_scope(act_scope)

        result = {
            "selected_fields": None, "selected_functions": None,
            "function_solved": False, "full_code": "", "full_ans": text,
            "exec_error": None, "solved_ans": "",
            "needs_user_input": False, "choices": choices,
            "paused": False, "completed": False,
            "db_context": None, "func_context": None, "search_result": None,
        }

        if action == "output_text":
            put_collapse("Output", [put_markdown(text, sanitize=False)], open=False)
        elif action == "ask_question":
            put_collapse("Question", [put_markdown(text, sanitize=False)], open=True)
            result["needs_user_input"] = True
        elif action == "ask_choice":
            put_collapse("Choice", [put_markdown(text, sanitize=False)], open=True)
            result["needs_user_input"] = True
        elif action == "summary_and_pause":
            put_collapse("Summary", [put_markdown(text, sanitize=False)], open=True)
            result["paused"] = True
        elif action == "attempt_completion":
            put_collapse("Completion", [put_markdown(text, sanitize=False)], open=False)
            result["completed"] = True

        return result
    except Exception as e:
        print(f"[ERROR] handle_frontend_action: action={action}, cycle={cycle_index}")
        print(f"[ERROR] action_result={json.dumps(action_result, ensure_ascii=False, default=str)}")
        traceback.print_exc()
        raise


def run_act_phase(cycle_index, action, full_question, selected_fields, selected_functions, conversation_history, session_id, action_result=None, params=None):
    try:
        if action in FRONTEND_ACTIONS:
            return handle_frontend_action(cycle_index, action, action_result or {})

        phase_header("act", f"ACT - {action} (Cycle {cycle_index})")
        act_scope = f"act_{cycle_index}"
        put_scope(act_scope)

        act_events = []
        append_exec = None
        append_code = None
        append_search = None
        search_scope_name = None
        for event in act_api_stream(
            action=action,
            question=full_question,
            tables=SELECT_TABLES,
            selected_fields=selected_fields,
            selected_functions=selected_functions,
            conversation_history=conversation_history,
            session_id=session_id,
            params=params,
        ):
            act_events.append(event)
            sub = event.get("sub_phase", "")
            etype = event.get("type", "")
            content = event.get("content", "")

            if sub in ("search_db", "search_func"):
                if append_search is None:
                    search_scope_name = f"act_{cycle_index}_search"
                    put_scope(search_scope_name)
                    append_search = display_streaming(search_scope_name, collapse_title=f"Search Results: {action}")
                append_search(event)
            elif sub in ("generate", "code"):
                if append_code is None:
                    code_scope = f"act_{cycle_index}_code"
                    put_scope(code_scope)
                    append_code = display_streaming(code_scope, collapse_title="Generated Code")
                append_code(event)
            elif sub == "exec":
                if append_exec is None:
                    exec_scope = f"act_{cycle_index}_exec"
                    put_scope(exec_scope)
                    append_exec = display_streaming(exec_scope, collapse_title="Execution Output")
                append_exec(event)
            elif sub in ("output_text", "summary", "completion", "ask_question", "ask_choice"):
                if append_exec is None:
                    out_scope = f"act_{cycle_index}_out"
                    put_scope(out_scope)
                    append_exec = display_streaming(out_scope, collapse_title="Output")
                append_exec(event)

        return parse_act_result(act_events)
    except Exception as e:
        print(f"[ERROR] run_act_phase: action={action}, cycle={cycle_index}")
        traceback.print_exc()
        raise


def run_observe_phase(cycle_index, original_question, current_plan, conversation_history, session_id, db_context=None, func_context=None):
    try:
        phase_header("observe", f"OBSERVE - Review (Cycle {cycle_index})")
        observe_scope = f"observe_{cycle_index}"
        put_scope(observe_scope)
        append_observe = display_streaming(observe_scope, collapse_title="Updated Plan")

        plan_str = json.dumps(current_plan, ensure_ascii=False) if isinstance(current_plan, dict) else str(current_plan)

        observe_events = []
        for event in observe_api_stream(
            original_question, SELECT_TABLES,
            current_plan=plan_str,
            conversation_history=conversation_history,
            cycle_index=cycle_index,
            session_id=session_id,
            db_context=db_context,
            func_context=func_context,
        ):
            observe_events.append(event)
            sub = event.get("sub_phase", "")
            etype = event.get("type", "")
            if sub == "review":
                append_observe({"type": etype, "content": event.get("content", "")})

        result = parse_observe_result(observe_events)
        with use_scope(observe_scope, clear=True):
            put_collapse("Updated Plan", [
                put_markdown(_format_plan_display(result), sanitize=False)
            ], open=False)
        return result
    except Exception as e:
        print(f"[ERROR] run_observe_phase: cycle={cycle_index}")
        traceback.print_exc()
        raise


def handle_user_interaction(act_result, conversation_history):
    """Handle user-facing actions: ask_question, ask_choice, summary_and_pause."""
    try:
        if act_result["needs_user_input"]:
            if act_result["choices"]:
                phase_header("user", "USER - Choice Required")
                user_choice = radio(
                    act_result["full_ans"],
                    options=[{"label": c, "value": c} for c in act_result["choices"]]
                )
                conversation_history.append(f"User chose: {user_choice}")
                return {"user_choice": user_choice}
            else:
                phase_header("user", "USER - Input Required")
                user_response = input(act_result["full_ans"], type=TEXT)
                conversation_history.append(f"User response: {user_response}")
                return {"user_response": user_response}

        if act_result["paused"]:
            put_info("Paused. Enter a new instruction or click Continue.")
            user_input = textarea("Continue or new instruction:", value="continue", type=TEXT, rows=2)
            if not user_input.strip():
                user_input = "continue"
            conversation_history.append(f"User: {user_input}")
            return {"user_response": user_input}

        if act_result["completed"]:
            put_success("Task completed.")
            return {"completed": True}

        return {}
    except Exception as e:
        print(f"[ERROR] handle_user_interaction: needs_user_input={act_result.get('needs_user_input')}, paused={act_result.get('paused')}, completed={act_result.get('completed')}")
        print(f"[ERROR] act_result keys={list(act_result.keys())}")
        traceback.print_exc()
        raise


def main():
    global SELECT_TABLES, SELECT_LABELS
    put_html(CURSOR_CSS)
    put_markdown("# Data-Copilot v3 (Think → Action → Act → Observe)")
    put_markdown("*One action per cycle. Action phase decides next step via LLM.*")

    put_markdown("### Control Panel")
    put_buttons(['Upload CSV File', 'Upload Document File'],
                onclick=[lambda: handle_csv_upload(), lambda: handle_doc_upload()])

    show_db_overview()

    session_id = datetime.now().strftime("%Y%m%d%H%M%S") + "".join(
        random.choices(string.ascii_letters, k=8)
    )
    put_markdown(f"Session ID: `{session_id}`")

    question = textarea("Enter your question here:", type=TEXT, rows=2)
    put_markdown("## " + question)

    conversation_history = [f"Q: {question}"]
    original_question = question
    current_plan = {"description": "", "todo": []}
    selected_fields = None
    selected_functions = None
    db_context = None
    func_context = None
    cycle_index = 0
    max_cycles = 20

    while True:
        try:
            cycle_index += 1

            if cycle_index > max_cycles:
                put_warning(f"Reached max cycles ({max_cycles}). Stopping.")
                break

            think_result = run_think_phase(
                cycle_index, question, conversation_history, session_id,
            )
            current_plan = think_result
            conversation_history = [e for e in conversation_history if not e.startswith("Planner: ")]
            conversation_history.append(f"Planner: {json.dumps(current_plan, ensure_ascii=False)}")

            if check_plan_complete(current_plan) and cycle_index == 1:
                current_plan = {"description": "", "todo": []}

            full_question = f"Context:\n" + "\n".join(conversation_history) + f"\n\nCurrent Question:\n{original_question}"

            action_result = run_action_phase(
                cycle_index, original_question,
                conversation_history, json.dumps(current_plan, ensure_ascii=False), db_context, func_context, session_id,
            )
            action = action_result.get("action")
            print(f"[DEBUG] action_result: {json.dumps(action_result, ensure_ascii=False, default=str)}")
            if not action:
                toast(f"Action failed: {action_result.get('error', 'unknown')}", color='error')
                break
            search_keyword = action_result.get("keyword")
            plan_funcs = action_result.get("funcs")

            act_funcs = plan_funcs if plan_funcs is not None else selected_functions
            act_fields = {"__no_db__": True} if action == "generate_and_execute" else selected_fields

            params = {}
            if search_keyword:
                params["search_keyword"] = search_keyword

            act_result = run_act_phase(
                cycle_index, action, full_question,
                act_fields, act_funcs,
                conversation_history, session_id,
                action_result=action_result,
                params=params,
            )
            print(f"[DEBUG] act_result: needs_user_input={act_result.get('needs_user_input')}, paused={act_result.get('paused')}, completed={act_result.get('completed')}, function_solved={act_result.get('function_solved')}")

            if act_result["db_context"]:
                db_context = act_result["db_context"]
            if act_result["func_context"]:
                func_context = act_result["func_context"]
            if act_result["selected_fields"] is not None:
                selected_fields = act_result["selected_fields"]
                conversation_history.append(f"Selected Fields: {json.dumps(selected_fields, ensure_ascii=False)}")
            if act_result["selected_functions"] is not None:
                selected_functions = act_result["selected_functions"]
                conversation_history.append(f"Selected Functions: {json.dumps(selected_functions, ensure_ascii=False)}")
            function_solved = act_result["function_solved"]
            full_code = act_result["full_code"]
            full_ans = act_result["full_ans"]
            exec_error = act_result["exec_error"]

            if function_solved:
                solved_ans = act_result["solved_ans"]
                if solved_ans:
                    conversation_history.append(f"A: {solved_ans}")
                    conversation_history = [e for e in conversation_history if not e.startswith("Planner: ")]
                continue

            if full_ans and not exec_error and full_code:
                conversation_history.append(f"Code Generated: {full_code}")
                conversation_history.append(f"Exe Result: {full_ans}")
            elif exec_error:
                if full_code:
                    conversation_history.append(f"Code Generated: {full_code}")
                conversation_history.append(f"Exe Error: {exec_error}")

            user_interaction = handle_user_interaction(act_result, conversation_history)
            if user_interaction.get("completed"):
                question = textarea("What is next?:", value="", type=TEXT, rows=2)
                if not question.strip():
                    continue
                put_markdown("## " + question)
                conversation_history.append(f"Q: {question}")
                original_question = question
                current_plan = {"description": "", "todo": []}
                selected_fields = None
                selected_functions = None
                db_context = None
                func_context = None
                continue

            observe_result = run_observe_phase(
                cycle_index, original_question,
                current_plan, conversation_history, session_id,
                db_context=db_context, func_context=func_context,
            )

            if observe_result.get("description"):
                current_plan = observe_result
                conversation_history = [e for e in conversation_history if not e.startswith("Planner: ")]
                conversation_history.append(f"Planner: {json.dumps(current_plan, ensure_ascii=False)}")

            if check_plan_complete(current_plan):
                put_info("Plan complete.")
                question = textarea("What is next?:", value="", type=TEXT, rows=2)
                if not question.strip():
                    continue
                put_markdown("## " + question)
                conversation_history.append(f"Q: {question}")
                original_question = question
                current_plan = {"description": "", "todo": []}
                selected_fields = None
                selected_functions = None
                db_context = None
                func_context = None
            else:
                put_info("Plan has pending tasks. Continuing to next action...")
        except Exception as e:
            print(f"[ERROR] main loop cycle={cycle_index}, action={action}")
            traceback.print_exc()
            toast(f"Error: {e}", color='error')
            break


if __name__ == '__main__':
    start_server(main, port=8039, debug=True)