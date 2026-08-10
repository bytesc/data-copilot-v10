import json
import re
import random
import string
import time
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
    selected_fields: Optional[dict] = None,
    conversation_history: Optional[List[str]] = None,
    session_id: str = "",
):
    payload = {"question": question, "session_id": session_id}
    if tables:
        payload["tables"] = tables
    if selected_fields is not None:
        payload["selected_fields"] = selected_fields
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
    user_response: Optional[str] = None,
    user_choice: Optional[str] = None,
    search_keyword: Optional[str] = None,
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
    if user_response:
        payload["user_response"] = user_response
    if user_choice:
        payload["user_choice"] = user_choice
    if search_keyword:
        payload["search_keyword"] = search_keyword
    yield from _sse_stream(f"{SERVER_URL}/api/act/stream/", payload)


def observe_api_stream(
    question: str,
    tables: Optional[List[str]] = None,
    selected_fields: Optional[dict] = None,
    execution_result: str = "",
    execution_error: str = "",
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
        "execution_result": execution_result,
        "execution_error": execution_error,
        "current_plan": current_plan,
        "cycle_index": cycle_index,
    }
    if tables:
        payload["tables"] = tables
    if selected_fields is not None:
        payload["selected_fields"] = selected_fields
    if conversation_history:
        payload["conversation_history"] = conversation_history
    if db_context:
        payload["db_context"] = db_context
    if func_context:
        payload["func_context"] = func_context
    yield from _sse_stream(f"{SERVER_URL}/api/observe/stream/", payload)


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
            with use_scope(scope_name, clear=True):
                if collapse_title and accumulated:
                    put_collapse(collapse_title, [
                        put_markdown(accumulated, sanitize=False)
                    ])
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


def parse_think_result(events: list) -> dict:
    result = {"plan": "", "next_action": None, "search_keyword": None}
    for event in events:
        sub = event.get("sub_phase", "")
        etype = event.get("type", "")
        content = event.get("content", "")
        if sub == "plan" and etype == "done":
            result["plan"] = content
            match = re.search(r'NEXT_ACTION:\s*(\w+)', content)
            if match:
                action = match.group(1)
                if action in ACTIONS:
                    result["next_action"] = action
            kw_match = re.search(r'keyword:\s*(\S+)', content)
            if kw_match:
                result["search_keyword"] = kw_match.group(1).rstrip(')')
    return result


def parse_act_result(events: list) -> dict:
    result = {
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

        if sub in ("search_db", "search_func") and etype == "done":
            result["search_result"] = content
            result["db_context"] = event.get("db_context") or result["db_context"]
            result["func_context"] = event.get("func_context") or result["func_context"]
            sf = event.get("selected_fields")
            if sf is not None:
                result["selected_fields"] = sf
            sfuncs = event.get("selected_functions")
            if sfuncs is not None:
                result["selected_functions"] = sfuncs

        if sub in ("output_text", "summary", "completion") and etype == "chunk":
            result["full_ans"] += content
        if sub in ("output_text", "summary", "completion") and etype == "done":
            result["full_ans"] = content

        if sub == "code" and etype == "code_complete":
            result["full_code"] = content
        if sub == "code" and etype == "solved":
            result["solved_ans"] = content
        if sub == "exec" and etype == "chunk":
            result["full_ans"] += content
        if sub == "exec" and etype == "error":
            result["exec_error"] = content

        if sub == "ask_question" and etype == "done":
            result["full_ans"] = content
            if event.get("needs_user_input"):
                result["needs_user_input"] = True

        if sub == "ask_choice" and etype == "done":
            result["full_ans"] = content
            result["choices"] = event.get("choices", [])
            if event.get("needs_user_input"):
                result["needs_user_input"] = True

        if sub == "summary" and etype == "done":
            if event.get("paused"):
                result["paused"] = True

        if sub == "completion" and etype == "done":
            if event.get("completed"):
                result["completed"] = True

    return result


def parse_observe_result(events: list) -> dict:
    result = {"updated_plan": "", "next_action": None, "search_keyword": None}
    for event in events:
        sub = event.get("sub_phase", "")
        etype = event.get("type", "")
        content = event.get("content", "")
        if sub == "review" and etype == "done":
            result["updated_plan"] = content
            match = re.search(r'NEXT_ACTION:\s*(\w+)', content)
            if match:
                action = match.group(1)
                if action in ACTIONS:
                    result["next_action"] = action
            kw_match = re.search(r'keyword:\s*(\S+)', content)
            if kw_match:
                result["search_keyword"] = kw_match.group(1).rstrip(')')
    return result


def check_plan_complete(plan: str) -> bool:
    if not plan:
        return True
    pending = re.findall(r'- \[ \]', plan)
    return len(pending) == 0


def determine_next_action(plan_result: dict, selected_fields, selected_functions):
    if plan_result.get("next_action"):
        return plan_result["next_action"]
    if selected_fields is None:
        return "search_db"
    if selected_functions is None:
        return "search_func"
    return "generate_and_execute"


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


def run_think_phase(cycle_index, question, selected_fields, conversation_history, session_id):
    label = f"THINK - Planning" if cycle_index == 0 else f"THINK - New Planning (Cycle {cycle_index + 1})"
    phase_header("think", label)
    think_scope = f"think_{cycle_index}"
    put_scope(think_scope)
    append_think = display_streaming(think_scope, collapse_title="Plan")

    think_events = []
    for event in think_api_stream(
        question, SELECT_TABLES,
        selected_fields=selected_fields,
        conversation_history=conversation_history,
        session_id=session_id,
    ):
        think_events.append(event)
        sub = event.get("sub_phase", "")
        etype = event.get("type", "")
        content = event.get("content", "")
        if sub == "plan":
            append_think({"type": etype, "content": content})

    return parse_think_result(think_events)


def run_act_phase(cycle_index, action, full_question, selected_fields, selected_functions, conversation_history, session_id, user_response=None, user_choice=None, search_keyword=None):
    phase_header("act", f"ACT - {action} (Cycle {cycle_index})")
    act_scope = f"act_{cycle_index}"
    put_scope(act_scope)

    act_events = []
    search_content = ""
    append_act = None
    for event in act_api_stream(
        action=action,
        question=full_question,
        tables=SELECT_TABLES,
        selected_fields=selected_fields,
        selected_functions=selected_functions,
        conversation_history=conversation_history,
        session_id=session_id,
        user_response=user_response,
        user_choice=user_choice,
        search_keyword=search_keyword,
    ):
        act_events.append(event)
        sub = event.get("sub_phase", "")
        etype = event.get("type", "")
        content = event.get("content", "")

        if sub in ("search_db", "search_func"):
            if etype == "chunk":
                search_content = content
            elif etype == "done":
                sf = event.get("selected_fields")
                sfuncs = event.get("selected_functions")
                json_display = ""
                if sf is not None:
                    json_display = f"```json\n{json.dumps(sf, ensure_ascii=False, indent=2)}\n```"
                elif sfuncs is not None:
                    json_display = f"```json\n{json.dumps(sfuncs, ensure_ascii=False, indent=2)}\n```"
                with use_scope(act_scope, clear=True):
                    put_collapse(f"Search Results: {action}", [
                        put_markdown(search_content, sanitize=False)
                    ], open=False)
                    if json_display:
                        put_text(f"Selection ({action}):")
                        put_markdown(json_display, sanitize=False)
        elif sub == "code" and etype == "code_complete":
            with use_scope(act_scope):
                put_collapse("Generated Code", [
                    put_markdown(f"```python\n{content}\n```", sanitize=False)
                ], open=False)
        elif sub == "exec":
            if append_act is None:
                exec_scope = f"act_{cycle_index}_exec"
                put_scope(exec_scope)
                append_act = display_streaming(exec_scope)
            append_act(event)
        elif sub in ("output_text", "summary", "completion", "ask_question", "ask_choice"):
            if append_act is None:
                out_scope = f"act_{cycle_index}_out"
                put_scope(out_scope)
                append_act = display_streaming(out_scope)
            append_act(event)

    return parse_act_result(act_events)


def run_observe_phase(cycle_index, original_question, selected_fields, full_ans, exec_error, current_plan, conversation_history, session_id, db_context=None, func_context=None):
    phase_header("observe", f"OBSERVE - Review (Cycle {cycle_index})")
    observe_scope = f"observe_{cycle_index}"
    put_scope(observe_scope)
    append_observe = display_streaming(observe_scope, collapse_title="Updated Plan")

    observe_events = []
    for event in observe_api_stream(
        original_question, SELECT_TABLES,
        selected_fields=selected_fields,
        execution_result=full_ans,
        execution_error=exec_error or "",
        current_plan=current_plan,
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

    return parse_observe_result(observe_events)


def handle_user_interaction(act_result, conversation_history):
    """Handle user-facing actions: ask_question, ask_choice, summary_and_pause."""
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


def main():
    global SELECT_TABLES, SELECT_LABELS
    put_html(CURSOR_CSS)
    put_markdown("# Data-Copilot v3 (Think → Act → Observe)")
    put_markdown("*One action per cycle. LLM-driven via NEXT_ACTION directive.*")

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
    current_plan = ""
    selected_fields = None
    selected_functions = None
    db_context = None
    func_context = None
    cycle_index = 0

    think_result = run_think_phase(
        cycle_index, question, selected_fields, conversation_history, session_id,
    )
    current_plan = think_result.get("plan", "")
    if current_plan:
        conversation_history.append(f"Planner: {current_plan}")

    while True:
        cycle_index += 1
        full_question = f"Context:\n" + "\n".join(conversation_history) + f"\n\nCurrent Question:\n{original_question}"

        action = determine_next_action(think_result, selected_fields, selected_functions)
        search_keyword = think_result.get("search_keyword")

        act_result = run_act_phase(
            cycle_index, action, full_question,
            selected_fields, selected_functions,
            conversation_history, session_id,
            search_keyword=search_keyword,
        )

        if act_result["db_context"]:
            db_context = act_result["db_context"]
        if act_result["func_context"]:
            func_context = act_result["func_context"]
        if act_result["selected_fields"] is not None:
            selected_fields = act_result["selected_fields"]
        if act_result["selected_functions"] is not None:
            selected_functions = act_result["selected_functions"]
        function_solved = act_result["function_solved"]
        full_code = act_result["full_code"]
        full_ans = act_result["full_ans"]
        exec_error = act_result["exec_error"]

        if function_solved:
            solved_ans = act_result["solved_ans"]
            if solved_ans:
                conversation_history.append(f"A: {solved_ans}")
                conversation_history = [e for e in conversation_history if not e.startswith("Planner: ")]
            current_plan = ""
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
            break

        observe_result = run_observe_phase(
            cycle_index, original_question, selected_fields,
            full_ans, exec_error, current_plan,
            conversation_history, session_id,
            db_context=db_context, func_context=func_context,
        )

        if observe_result.get("updated_plan"):
            current_plan = observe_result["updated_plan"]
            conversation_history = [e for e in conversation_history if not e.startswith("Planner: ")]
            conversation_history.append(f"Planner: {current_plan}")

        think_result = observe_result

        if check_plan_complete(current_plan):
            put_info("Plan complete.")
            question = textarea("What is next?:", value="", type=TEXT, rows=2)
            if not question.strip():
                continue
            put_markdown("## " + question)
            conversation_history.append(f"Q: {question}")
            original_question = question

            think_result = run_think_phase(
                cycle_index, question, selected_fields, conversation_history, session_id,
            )
            current_plan = think_result.get("plan", "")
            if current_plan:
                conversation_history = [e for e in conversation_history if not e.startswith("Planner: ")]
                conversation_history.append(f"Planner: {current_plan}")
        else:
            put_info("Plan has pending tasks. Continuing to next action...")


if __name__ == '__main__':
    start_server(main, port=8039, debug=True)