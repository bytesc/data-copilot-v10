from sqlalchemy import inspect

from .tools.copilot.sql_code import get_db_info_prompt
from .tools.tools_def import engine, llm
from utils.column_ddl import build_column_comment_sql, build_table_comment_sql
from utils.context_trim import call_with_context_retry, cap_text
from utils.json_parse import parse_json


def get_llm_data_comment_func(txt, table):
    """Ask the LLM for structured comments and return them as a dict.

    The LLM must NOT emit SQL here: it only returns a JSON object describing
    the table comment and per-column comments. The DDL is built and executed
    server-side (see ``_apply_table_comments``) so a compromised / injected
    document can never smuggle arbitrary statements into the database.
    """
    data_str = get_db_info_prompt(engine, simple=True, example=False, tables=[table])

    pre_prompt = """
Please read the document and generate comments for the table and its columns.
Here is the document:
"""

    end_prompt = """
Reminders:
1. Output ONLY a single JSON object, with NO markdown code block, NO explanations and NO SQL.
2. "columns" MUST only use column names that exist in the table structure above; omit any column you are not confident about.
3. Keep comments short and clear. Column comments should be no more than 20 words. Table comments should be no more than 100 words.
4. Do NOT output any ALTER TABLE / DROP / DELETE / INSERT / UPDATE statement.

Required JSON shape:
{"table_comment": "...", "columns": {"column_name": "comment", ...}}
"""

    def build_prompt(level):
        return pre_prompt + cap_text(txt, level) + "\n" + \
            "Here is the table structure: \n" + cap_text(data_str, level) + """
Only generate comments for the specified table name:
""" + table + "\n" + end_prompt

    ans = call_with_context_retry(build_prompt, llm)
    result = parse_json(ans.content)
    if not isinstance(result, dict):
        print("[WARNING] Data comment generation did not return valid JSON.")
        return None
    return result


def _apply_table_comments(engine, table_name, data):
    """Apply LLM-produced comments using schema-validated, server-built DDL.

    Only the target table is touched, column names are whitelisted against the
    real schema, and the column definition is taken from ``SHOW CREATE TABLE``
    so charset/collation/default/auto_increment/generated attributes are kept.
    """
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        print(f"[WARNING] Table '{table_name}' not found; skipping comment update.")
        return False

    valid_columns = {c["name"] for c in inspector.get_columns(table_name)}
    table_comment = data.get("table_comment")
    comments = data.get("columns")
    if not isinstance(comments, dict):
        comments = {}

    with engine.connect() as conn:
        if table_comment and str(table_comment).strip():
            conn.exec_driver_sql(build_table_comment_sql(conn, table_name, table_comment))
        for col_name, comment in comments.items():
            if col_name not in valid_columns:
                continue
            if comment is None or not str(comment).strip():
                continue
            conn.exec_driver_sql(build_column_comment_sql(conn, table_name, col_name, comment))
        conn.commit()
    return True


def get_llm_data_comment(extracted_text, table_name):
    data = get_llm_data_comment_func(extracted_text, table_name)
    if not isinstance(data, dict):
        print("[WARNING] No table/column comments were generated; skipping comment update.")
        return False
    return _apply_table_comments(engine, table_name, data)
