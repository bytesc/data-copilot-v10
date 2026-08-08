import json
import random
import string
from datetime import datetime
from typing import Optional, List
import base64
from pywebio.session import set_env
from pywebio.input import input, TEXT, textarea, file_upload, select, checkbox
from pywebio.output import put_text, put_html, put_markdown, clear, put_loading, toast, popup, put_buttons, \
    put_collapse, put_table, use_scope, put_scope
from pywebio import start_server, config
from data_access.read_db import get_rows_from_all_tables, get_table_comments_dict, get_all_comments_from_table
from utils.front_utils import (
    ai_agent_api, generate_code_stream, execute_code_stream,
    step_chat_api_stream, filter_db_fields_stream, filter_functions_stream, upload_csv_api,
    plain_chat_api_stream, upload_doc_api, download_image, markdown_to_word,
    export_full_to_word, export_essentials_to_word
)


SELECT_TABLES = []
SELECT_LABELS = []


def handle_export_word(conversation_history, export_type="full"):
    """Handle Word document export"""
    if not conversation_history:
        toast("No content to export!", color='warning')
        return

    with put_loading(shape="grow", color="primary"):
        try:
            if export_type == "full":
                word_file = export_full_to_word(conversation_history)
                filename = "conversation_export_full.docx"
            else:
                word_file = export_essentials_to_word(conversation_history)
                filename = "conversation_export_essentials.docx"

            file_content = word_file.getvalue()
            b64 = base64.b64encode(file_content).decode()

            download_script = f'''
            <script>
                var link = document.createElement('a');
                link.href = 'data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,{b64}';
                link.download = '{filename}';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            </script>
            '''

            put_html(download_script)
            toast(f"Download started: {filename}", color='success')

        except Exception as e:
            toast(f"Export failed: {str(e)}", color='error')


def handle_csv_upload():
    file_info = file_upload(
        "Please select a CSV file to upload",
        accept=".csv",
        help_text="Select the CSV file you want to upload"
    )

    if file_info:
        table_name = input("Enter table name (optional, default is 'uploaded_data')", type=TEXT,
                           placeholder="uploaded_data", required=False)
        if not table_name:
            table_name = "uploaded_data"
        with put_loading(shape="grow", color="primary"):
            result = upload_csv_api(file_info['content'], table_name)
            print(result)
        err = result.get('type', "error")
        if err == "error":
            toast(f"Upload failed: {result}", color='error')
        else:
            toast("File uploaded successfully!", color='success')
            put_markdown("### Upload Results")
            put_markdown(f"Table name: `{result.get('table_name', table_name)}`")
            put_markdown(f"Row count: {result.get('row_count', 'N/A')}")
            put_markdown(f"Message: {result.get('message', 'N/A')}")


def handle_doc_upload():
    file_info = file_upload(
        "Please select a document file to upload (txt, doc, docx, pdf)",
        accept=".txt,.doc,.docx,.pdf",
        help_text="Select the document file you want to upload"
    )

    if file_info:
        table_name = input("Enter table name (optional, default is 'uploaded_data')", type=TEXT,
                           placeholder="uploaded_data", required=False)
        if not table_name:
            table_name = "uploaded_data"
        with put_loading(shape="grow", color="primary"):
            result = upload_doc_api(file_info['content'], file_info['filename'], table_name)
            print(result)

        if result.get('error'):
            toast(f"Upload failed: {result.get('error')}", color='error')
        else:
            toast("File uploaded successfully!", color='success')
            put_markdown("### Upload Results")
            put_markdown(f"Table name: `{result.get('table_name', table_name)}`")
            put_markdown(f"Extracted text length: {result.get('extracted_text_length', 'N/A')}")
            put_markdown(f"Preview: {result.get('preview', 'N/A')}")


def handle_table_selection(table_options):
    global SELECT_TABLES, SELECT_LABELS
    checkbox_options = [(opt['label'], opt['value']) for opt in table_options]
    selected_tables = checkbox(
        "Select tables: ",
        options=checkbox_options,
        inline=True
    )
    SELECT_TABLES = selected_tables
    put_markdown(f"You have selected: `{', '.join(selected_tables)}`")
    if selected_tables:
        selected_labels = []
        for table_value in selected_tables:
            for opt in table_options:
                if opt['value'] == table_value:
                    selected_labels.append(opt['label'])
                    break
        SELECT_LABELS = selected_labels


CURSOR = '<span class="blink-cursor">|</span>'

CURSOR_CSS = '''
<style>
.blink-cursor {
    animation: blink 1s step-end infinite;
    font-weight: bold;
}
@keyframes blink {
    50% { opacity: 0; }
}
</style>
'''


def display_streaming_response(scope_name, collapse_title=None):
    """Return a callback to append streaming content in the specified scope"""
    accumulated = ""
    handled = False

    def append_chunk(event):
        nonlocal accumulated, handled
        event_type = event.get("type")
        if event_type == "status":
            toast(event["content"], color='info')
        elif event_type in ("chunk", "code_chunk"):
            accumulated += event["content"]
            with use_scope(scope_name, clear=True):
                put_markdown(accumulated, sanitize=False)
                put_html(CURSOR)
        elif event_type == "code_complete":
            handled = True
            accumulated = "```python\n" + event["content"] + "\n```"
            with use_scope(scope_name, clear=True):
                put_collapse("📝 Generated Code", [put_markdown(accumulated, sanitize=False)], open=False)
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
                    put_collapse(collapse_title, [put_markdown(accumulated, sanitize=False)])
                elif accumulated:
                    put_markdown(accumulated, sanitize=False)
        elif event_type == "error":
            toast(event["content"], color='error')
            with use_scope(scope_name, clear=False):
                put_markdown(f"\n\n**Error:** {event['content']}", sanitize=False)
        return accumulated

    return append_chunk


def main():
    global SELECT_TABLES, SELECT_LABELS
    put_html(CURSOR_CSS)
    put_markdown("# Data-Copilot (Streaming)")

    first_five_rows = get_rows_from_all_tables()

    table_comments = get_table_comments_dict()
    table_options = []
    for table_name, comment in table_comments.items():
        display_name = f"{table_name} ({comment})" if comment else table_name
        table_options.append({'label': display_name, 'value': table_name})

    put_markdown("### Control Panel")
    put_buttons(['Select Tables', 'Upload CSV File', 'Upload Document File'],
                onclick=[lambda: handle_table_selection(table_options), handle_csv_upload, handle_doc_upload])

    put_markdown("### Export Options")
    put_buttons(['Export Full Conversation', 'Export Essentials (Answers)'],
                onclick=[lambda: handle_export_word(conversation_history, "full"),
                         lambda: handle_export_word(conversation_history, "essentials")])

    put_markdown("### 📊 Data View")
    with put_collapse(f"📋 Tables"):
        all_comments = get_all_comments_from_table()
        first_five_rows = get_rows_from_all_tables()

        for table_name, rows in first_five_rows.items():
            with put_collapse(f" table {table_name}"):
                if table_name in all_comments:
                    table_comment = all_comments[table_name].get('table_comment', '')
                    if table_comment:
                        put_text(f"📝 {table_comment}")

                    columns = all_comments[table_name].get('columns', {})
                    if columns:
                        comment_table = [["Column Name", "Comment"]]
                        for col_name, comment in columns.items():
                            comment_table.append([col_name, comment])
                        put_table(comment_table)

                put_text(f"📊 table {table_name} first 5 rows:")
                put_table([rows.columns.tolist()] + rows.values.tolist())

    conversation_history = []
    conversation_session_id = datetime.now().strftime("%Y%m%d%H%M%S") + "".join(random.choices(string.ascii_letters, k=8))
    put_markdown(conversation_session_id)

    question = textarea("Enter your question here:", type=TEXT, rows=2)
    put_markdown("## " + question)
    conversation_history.append(f"Q: {question}")

    filter_scope = f"filter_scope_initial"
    put_scope(filter_scope)
    filter_content = ""
    selected_fields = None
    for event in filter_db_fields_stream(question, SELECT_TABLES):
        event_type = event.get("type")
        if event_type == "status":
            toast(event["content"], color='info')
        elif event_type == "chunk":
            filter_content += event["content"]
            with use_scope(filter_scope, clear=True):
                put_markdown(filter_content, sanitize=False)
                put_html(CURSOR)
        elif event_type == "done":
            filter_content = event.get("content", "")
            import re as _re
            match = _re.search(r'```json\s*(.*?)\s*```', filter_content, _re.DOTALL)
            if match:
                try:
                    selected_fields = json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            with use_scope(filter_scope, clear=True):
                if isinstance(selected_fields, dict) and selected_fields.get("__no_db__"):
                    put_collapse("🔍 Database Field Filter", [put_markdown("No database query needed.", sanitize=False)])
                elif selected_fields and not selected_fields.get("__no_db__"):
                    put_collapse("🔍 Database Field Filter", [
                        put_markdown("```json\n" + json.dumps(selected_fields, ensure_ascii=False, indent=2) + "\n```", sanitize=False)
                    ])
                else:
                    put_collapse("🔍 Database Field Filter", [put_markdown("```json\n" + filter_content + "\n```", sanitize=False)])
        elif event_type == "error":
            toast(event["content"], color='warning')
            selected_fields = None

    if selected_fields is not None and len(selected_fields) == 0:
        selected_fields = None

    scope_name = f"plan_scope"
    put_scope(scope_name)
    append_plan = display_streaming_response(scope_name, collapse_title="📋 Analysis Plan")
    full_plan = ""
    for event in step_chat_api_stream(question, SELECT_TABLES,
                                      selected_fields=selected_fields,
                                      session_id=conversation_session_id):
        full_plan = append_plan(event)
    if full_plan:
        conversation_history.append(f"Planner: {full_plan}")
    else:
        put_text("Failed to get a response from the AI Agent.")

    while True:
        table_pre = ""

        import re as _re2
        plan_complete = False
        for entry in reversed(conversation_history):
            if entry.startswith("Planner: "):
                plan_text = entry[9:]
                pending = _re2.findall(r'- \[ \]', plan_text)
                plan_complete = len(pending) == 0
                break

        if plan_complete:
            value = ""
        else:
            value = "please do the next step on the todo list"
        question = textarea("What is next?:", value=value, type=TEXT, rows=2)
        if not question.strip():
            continue
        put_markdown("## " + question)
        if conversation_history:
            context = "\n".join(conversation_history)
            full_question = f"Context:\n{context}\n\nCurrent Question:\n{question}"
        else:
            full_question = question

        selected_fields = None

        for value in [question]:
            function_scope = f"function_scope_{len(conversation_history)}"
            put_scope(function_scope)
            function_content = ""
            selected_functions = None
            function_solved = False
            for event in filter_functions_stream(table_pre + full_question):
                event_type = event.get("type")
                if event_type == "status":
                    toast(event["content"], color='info')
                elif event_type == "chunk":
                    function_content += event["content"]
                    with use_scope(function_scope, clear=True):
                        put_markdown(function_content, sanitize=False)
                        put_html(CURSOR)
                elif event_type == "done":
                    function_content = event.get("content", "")
                    selected_functions = event.get("selected_functions")
                    function_solved = event.get("solved", False)
                    with use_scope(function_scope, clear=True):
                        if function_solved:
                            put_collapse("🔧 Function Selection", [
                                put_markdown("No functions needed, direct answer.", sanitize=False),
                                put_markdown("```\n" + function_content + "\n```", sanitize=False)
                            ])
                        elif selected_functions is not None:
                            if selected_functions:
                                put_collapse("🔧 Function Selection", [
                                    put_markdown("Selected: `" + ", ".join(selected_functions) + "`", sanitize=False),
                                    put_markdown("```\n" + function_content + "\n```", sanitize=False)
                                ])
                            else:
                                put_collapse("🔧 Function Selection", [
                                    put_markdown("All functions will be used.", sanitize=False),
                                    put_markdown("```\n" + function_content + "\n```", sanitize=False)
                                ])
                elif event_type == "error":
                    toast(event["content"], color='warning')

            if function_solved:
                conversation_history.append(f"Q: {question}")
                conversation_history.append(f"A: {function_content}")
                context = "\n".join(conversation_history)
                full_question = f"Context:\n{context}\n"

            filter_scope = f"filter_scope_{len(conversation_history)}"
            put_scope(filter_scope)
            filter_content = ""
            selected_fields = None
            for event in filter_db_fields_stream(table_pre + full_question, SELECT_TABLES):
                event_type = event.get("type")
                if event_type == "status":
                    toast(event["content"], color='info')
                elif event_type == "chunk":
                    filter_content += event["content"]
                    with use_scope(filter_scope, clear=True):
                        put_markdown(filter_content, sanitize=False)
                        put_html(CURSOR)
                elif event_type == "done":
                    filter_content = event.get("content", "")
                    import re as _re
                    match = _re.search(r'```json\s*(.*?)\s*```', filter_content, _re.DOTALL)
                    if match:
                        try:
                            selected_fields = json.loads(match.group(1))
                        except json.JSONDecodeError:
                            pass
                    with use_scope(filter_scope, clear=True):
                        if isinstance(selected_fields, dict) and selected_fields.get("__no_db__"):
                            put_collapse("🔍 Database Field Filter", [put_markdown("No database query needed.", sanitize=False)])
                        elif selected_fields and not selected_fields.get("__no_db__"):
                            put_collapse("🔍 Database Field Filter", [
                                put_markdown("```json\n" + json.dumps(selected_fields, ensure_ascii=False, indent=2) + "\n```", sanitize=False)
                            ])
                        else:
                            put_collapse("🔍 Database Field Filter", [put_markdown("```json\n" + filter_content + "\n```", sanitize=False)])
                elif event_type == "error":
                    toast(event["content"], color='warning')
                    selected_fields = None

            if selected_fields is not None and len(selected_fields) == 0:
                selected_fields = None

            if function_solved:
                ans_scope = f"ans_scope_{len(conversation_history)}"
                put_scope(ans_scope)
                append_ans = display_streaming_response(ans_scope)
                full_ans = ""
                for event in plain_chat_api_stream(table_pre + full_question, SELECT_TABLES,
                                                   selected_fields=selected_fields,
                                                   session_id=conversation_session_id):
                    full_ans = append_ans(event)
                if full_ans:
                    conversation_history.append(f"Q: {question}")
                    conversation_history.append(f"A: {full_ans}")
                else:
                    put_text("Failed to get a response from the AI Agent.")
            else:
                code_scope = f"code_scope_{len(conversation_history)}"
                put_scope(code_scope)
                append_code = display_streaming_response(code_scope)
                full_code = ""
                solved_ans = ""
                for event in generate_code_stream(table_pre + full_question, SELECT_TABLES,
                                                  selected_fields=selected_fields,
                                                  selected_functions=selected_functions,
                                                  session_id=conversation_session_id):
                    append_code(event)
                    if event.get("type") == "code_complete":
                        full_code = event["content"]
                    elif event.get("type") == "solved":
                        solved_ans = event["content"]

                if full_code:
                    ans_scope = f"ans_scope_{len(conversation_history)}"
                    put_scope(ans_scope)
                    append_ans = display_streaming_response(ans_scope)
                    full_ans = ""
                    for event in execute_code_stream(full_code, session_id=conversation_session_id):
                        full_ans = append_ans(event)
                    if full_ans:
                        conversation_history.append(f"Q: {question}")
                        conversation_history.append(f"A: {full_ans}")
                elif solved_ans:
                    conversation_history.append(f"Q: {question}")
                    conversation_history.append(f"A: {solved_ans}")
                else:
                    put_text("Failed to get a response from the AI Agent.")

                context = "\n".join(conversation_history)
                full_question = f"Context:\n{context}\n"
        else:
            context = "\n".join(conversation_history)
            full_question = f"Context:\n{context}\n\nCurrent Question:\n{question}"

        plan_scope = f"plan_scope_{len(conversation_history)}"
        put_scope(plan_scope)
        append_plan = display_streaming_response(plan_scope, collapse_title="📋 Analysis Plan")
        full_plan = ""
        for event in step_chat_api_stream(table_pre + full_question, SELECT_TABLES,
                                          selected_fields=selected_fields,
                                          session_id=conversation_session_id):
            full_plan = append_plan(event)
        if full_plan:
            conversation_history.append(f"Planner: {full_plan}")
        else:
            put_text("Failed to get a response from the AI Agent.")


if __name__ == '__main__':
    start_server(main, port=8038, debug=True)
