import json
import logging
import re

from .utils.read_db import get_table_creation_statements, get_rows_from_all_tables, \
    get_table_and_column_comments, get_all_comments
from .utils.call_llm_test import call_llm, call_llm_stream
from .utils.parse_output import parse_generated_sql_code
from .utils.read_db import execute_select

def get_db_info_prompt(engine, simple=False, example=False, tables=None, selected_fields=None):
    data_prompt = """
Here is the structure of the database:
"""
    data_prompt += "\n```sql\n"+str(get_table_creation_statements(engine, tables, simple, selected_fields))+"\n```\n"
    data_prompt += """
Here is the table and column comments:
"""
    data_prompt += str(get_table_and_column_comments(engine, tables, selected_fields))
    if example:
        data_prompt += """
Here is data samples(just samples, do not mock any data):
"""
        data_prompt += str(get_rows_from_all_tables(engine, tables, 1, selected_fields))

    other_info = """
    Use MySql Dialect.
    """
    data_prompt += other_info
    return data_prompt


def get_sql_code(question, df_cols, llm, engine, retries=3):
    retries_times = 0
    error_msg = ""
    # print(get_table_creation_statements(engine, tables))
    # print(get_table_and_column_comments(engine, tables))
    # print(get_rows_from_all_tables(engine, tables, 3))
    while retries_times <= retries:
        retries_times += 1
        pre_prompt = """
Please write SQL code to select the data needed according to the following requirements:
"""

        data_prompt = get_db_info_prompt(engine, example=True)

        if df_cols:
            data_prompt += "With output columns names: \n"
            data_prompt += str(df_cols) + "\n"

        end_prompt = """
Remind:
1. All code should be completed in a single markdown code block without any comments, explanations or cmds.
"""
        final_prompt = question + pre_prompt + "\n" + data_prompt + end_prompt

        ans = call_llm(final_prompt + error_msg, llm)
        print("sql################################3")
        print(ans.content)
        result_sql = parse_generated_sql_code(ans.content)
        if result_sql is None:
            error_msg = """
code should only be in a md code block: 
```sql
# some sql code
```
without any additional comments, explanations or cmds !!!
"""
            print(ans + "No code was generated.")
            continue
        else:
            return result_sql


def query_database_func(question, df_cols, llm, engine, retries=2):
    exp = None
    for i in range(retries):
        err_msg = ""
        for j in range(retries):
            sql = get_sql_code(question + err_msg, df_cols, llm, engine)
            # print(sql)
            if sql is None:
                continue
            try:
                result = execute_select(engine, sql)
                logging.info(f"query_database_SQL: {sql}\nQuestion: {question}\nResult: {result}\n")
                return result
            except Exception as e:
                err_msg = str(e)
                exp = e
                print(e)
                continue
    return None


def _build_compact_schema(engine, tables=None):
    all_comments = get_all_comments(engine, tables)
    lines = []
    for table_name, info in all_comments.items():
        table_comment = info.get('table_comment', '')
        header = f"Table: {table_name}"
        if table_comment:
            header += f"  ({table_comment})"
        lines.append(header)
        columns = info.get('columns', {})
        for col_name, col_comment in columns.items():
            lines.append(f"  - {col_name}: {col_comment}")
        if not columns:
            lines.append("  (no column comments)")
        lines.append("")
    return "\n".join(lines)


def parse_selected_fields_json(txt):
    try:
        match = re.search(r'```json\s*(.*?)\s*```', txt, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return json.loads(txt)
    except Exception:
        try:
            match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', txt, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception:
            pass
    return None


def _build_filter_prompt(question, engine, tables=None):
    schema = _build_compact_schema(engine, tables)
    return f"""You are a database analysis assistant. Analyze the following input to determine which database tables and columns are needed:

"{question}"

Below is the structure and comments of all database tables:

{schema}

The input above may contain conversation history, a step-by-step plan, and the current task. Your job is to identify which database tables and columns are needed to execute the current task described in the plan.

Requirements:
1. Read the plan carefully - if it mentions any data retrieval, table operations, or database queries, you MUST select the relevant tables and columns
2. Only select tables and columns directly relevant to the current task
3. Do not include a table if none of its columns are relevant
4. If only some columns of a table are relevant, include only those columns
5. If ALL columns of a table are relevant, use an empty list [] to indicate all columns
6. Must include key columns used for table joins (e.g., foreign keys, IDs)

Output rules:
- Use `{{"table_name": ["col1", "col2"]}}` to select specific columns
- Use `{{"table_name": []}}` to select ALL columns of a table
- Use `{{}}` to select ALL tables and ALL columns
- Use `{{"__no_db__": true}}` ONLY if the current task is purely conversational (greeting, clarification, etc.) and requires NO data access whatsoever

Please strictly output in the following JSON format, without any additional explanation:

```json
{{
    "table_name_1": ["column_a", "column_b", "id"],
    "table_name_2": []
}}
```

Select specific columns:
```json
{{
    "users": ["id", "name", "age"]
}}
```

Select all columns of a table:
```json
{{
    "users": [],
    "orders": []
}}
```

Select all tables and all columns:
```json
{{}}
```

No database query needed (only for pure conversation):
```json
{{
    "__no_db__": true
}}
```"""


def filter_db_fields(question, engine, llm, tables=None, retries=2):
    prompt = _build_filter_prompt(question, engine, tables)

    for attempt in range(retries):
        response = call_llm(prompt, llm)
        result = parse_selected_fields_json(response.content)
        if result is not None and isinstance(result, dict):
            logging.info(f"filter_db_fields: Question: {question}\nResult: {result}\n")
            return result
        print(f"filter_db_fields parse failed (attempt {attempt+1}), raw: {response.content[:200]}")

    return None


def filter_db_fields_stream(question, engine, llm, tables=None):
    yield {"type": "status", "content": "正在分析数据库结构..."}
    yield {"type": "status", "content": "正在筛选相关表和字段..."}

    prompt = _build_filter_prompt(question, engine, tables)
    full_content = ""

    for chunk in call_llm_stream(prompt, llm):
        full_content += chunk
        yield {"type": "chunk", "content": chunk}

    result = parse_selected_fields_json(full_content)
    if result is not None and isinstance(result, dict):
        logging.info(f"filter_db_fields_stream: Question: {question}\nResult: {result}\n")
        yield {"type": "done", "content": full_content, "selected_fields": result}
    else:
        yield {"type": "error", "content": "字段筛选解析失败", "selected_fields": None}
