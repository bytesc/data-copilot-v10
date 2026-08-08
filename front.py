import random
import string
from datetime import datetime
from typing import Optional, List
import base64
from pywebio.session import set_env
from pywebio.input import input, TEXT, textarea, file_upload, select, checkbox
from pywebio.output import put_text, put_html, put_markdown, clear, put_loading, toast, popup, put_buttons, \
    put_collapse, put_table
from pywebio import start_server, config
from data_access.read_db import get_rows_from_all_tables, get_table_comments_dict, get_all_comments_from_table
from utils.front_utils import (
    ai_agent_api, upload_csv_api, upload_doc_api,
    markdown_to_word, export_full_to_word, export_essentials_to_word
)


SELECT_TABLES = []
SELECT_LABELS = []


def handle_export_word(conversation_history, export_type="full"):
    """处理导出Word文档 - 直接下载"""
    if not conversation_history:
        toast("No content to export!", color='warning')
        return

    with put_loading(shape="grow", color="primary"):
        try:
            if export_type == "full":
                word_file = export_full_to_word(conversation_history)
                filename = "conversation_export_full.docx"
            else:  # essentials
                word_file = export_essentials_to_word(conversation_history)
                filename = "conversation_export_essentials.docx"

            # 读取文件内容并编码为base64用于直接下载
            file_content = word_file.getvalue()
            b64 = base64.b64encode(file_content).decode()

            # 使用JavaScript触发直接下载
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


def main():
    global SELECT_TABLES, SELECT_LABELS
    put_markdown("# Data-Copilot")

    first_five_rows = get_rows_from_all_tables()

    table_comments = get_table_comments_dict()
    table_options = []
    for table_name, comment in table_comments.items():
        display_name = f"{table_name} ({comment})" if comment else table_name
        table_options.append({'label': display_name, 'value': table_name})

    # 添加表格选择、上传和导出按钮
    put_markdown("### Control Panel")
    put_buttons(['Select Tables', 'Upload CSV File', 'Upload Document File'],
                onclick=[lambda: handle_table_selection(table_options), handle_csv_upload, handle_doc_upload])

    put_markdown("### Export Options")
    put_buttons(['Export Full Conversation', 'Export Essentials (Answers)'],
                onclick=[lambda: handle_export_word(conversation_history, "full"),
                         lambda: handle_export_word(conversation_history, "essentials")])

    # with put_collapse(f"Tables Preview"):
    #     for table_name, rows in first_five_rows.items():
    #         with put_collapse(f"table {table_name}"):
    #             put_text(f"table {table_name} first 5 rows:")
    #             put_table([rows.columns.tolist()] + rows.values.tolist())

    put_markdown("### 📊 Data View")
    with put_collapse(f"📋 Tables"):
        # 获取所有注释信息
        all_comments = get_all_comments_from_table()
        first_five_rows = get_rows_from_all_tables()

        for table_name, rows in first_five_rows.items():
            with put_collapse(f" table {table_name}"):
                # 显示表注释
                if table_name in all_comments:
                    table_comment = all_comments[table_name].get('table_comment', '')
                    if table_comment:
                        put_text(f"📝 {table_comment}")

                    # 显示列注释（表格形式）
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
    with put_loading():
        step_str, _, conversation_session_id = ai_agent_api(question, SELECT_TABLES, "/api/step-chat/", session_id=conversation_session_id)
    if step_str:
        # step_str = textarea("revise plan:", type=TEXT, rows=8, value=step_str)
        conversation_history.append(f"Planner: {step_str}")
        put_markdown(step_str, sanitize=False)
    else:
        put_text("Failed to get a response from the AI Agent.")

    while True:
        table_pre = ""

        value = "please do the next step on the todo list"
        question = textarea("What is next?:", value=value, type=TEXT, rows=2)
        put_markdown("## " + question)
        if conversation_history:
            context = "\n".join(conversation_history)
            full_question = f"Context:\n{context}\n\nCurrent Question:\n{question}"
        else:
            full_question = question

        if value == question:
            with put_loading():
                response, code, conversation_session_id = ai_agent_api(table_pre + full_question, SELECT_TABLES, "/api/ask-agent/", session_id=conversation_session_id)
            if response:
                conversation_history.append(f"Q: {question}")
                conversation_history.append(f"Code Generated: {code}")
                conversation_history.append(f"A: {response}")
                put_markdown(response, sanitize=False)
                time.sleep(3)
            else:
                put_text("Failed to get a response from the AI Agent.")

            context = "\n".join(conversation_history)
            full_question = f"Context:\n{context}\n"
        else:
            context = "\n".join(conversation_history)
            full_question = f"Context:\n{context}\n\nCurrent Question:\n{question}"

        with put_loading():
            step_str, _, conversation_session_id = ai_agent_api(table_pre + full_question, SELECT_TABLES, "/api/step-chat/", session_id=conversation_session_id)
        if step_str:
            # step_str = textarea("revise plan:", type=TEXT, rows=8, value=step_str)
            conversation_history.append(f"Planner: {step_str}")
            put_markdown(step_str, sanitize=False)
        else:
            put_text("Failed to get a response from the AI Agent.")


if __name__ == '__main__':
    start_server(main, port=8037, debug=True)
