import json
import logging
import re

from .utils.read_db import get_table_creation_statements, get_rows_from_all_tables, \
    get_table_and_column_comments, get_all_comments
from utils.context_trim import call_with_context_retry, stream_with_context_retry, cap_text

def get_db_info_prompt(engine, simple=False, example=False, tables=None, selected_fields=None):
    data_prompt = """
Here is the structure of the database:
"""
    data_prompt += "\n```sql\n"+str(get_table_creation_statements(engine, tables, simple, selected_fields))+"\n```\n"
    table_comments, column_comments = get_table_and_column_comments(engine, tables, selected_fields)
    if table_comments:
        data_prompt += "\nTable comments:\n"
        for tname, tcomment in table_comments.items():
            data_prompt += f"- {tname}: {tcomment}\n"
    if column_comments:
        data_prompt += "\nColumn comments:\n"
        for tname, ccols in column_comments.items():
            for cname, ccomment in ccols.items():
                data_prompt += f"- {tname}.{cname}: {ccomment}\n"
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
    from utils.json_parse import parse_json
    result = parse_json(txt)
    if result is not None:
        return result
    try:
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', txt, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return None


def _build_filter_prompt(question, engine, tables=None, level=0):
    schema = cap_text(_build_compact_schema(engine, tables), level)
    question = cap_text(question, level)
    empty_json = "{}"
    return f"""You are a database analysis assistant. Analyze the following input to determine which database tables and columns are needed:

"{question}"

Below is the structure and comments of all database tables:

{schema}

The input above may contain conversation history, a step-by-step plan, and the current task. Your job is to identify which database tables and columns are needed to execute the current task described in the plan.

Requirements:
1. If the user mentions ANY of these keywords: analysis, analyze, data, query, graph, chart, plot, visualization, statistics, report, explore, inspect, look at, show, display, select, filter, group, count, average, sum, min, max, trend, distribution, comparison, or any data-related operation that requires fetching data from the database, you MUST select relevant tables and columns. NEVER return `__no_db__` for data-fetching requests.
2. If the user's request is vague but related to data/analysis, select ALL tables and ALL columns by returning `{empty_json}`.
3. Only select tables and columns directly relevant to the current task.
4. If only some columns of a table are relevant, include only those columns.
5. If ALL columns of a table are relevant, use an empty list [] to indicate all columns.
6. Must include key columns used for table joins (e.g., foreign keys, IDs).
7. If the task is to summarize, conclude, explain, or describe content that is already in the conversation history or previous execution results, do NOT query the database. Return `__no_db__` instead.

Output rules:
- Use `{{"table_name": ["col1", "col2"]}}` to select specific columns
- Use `{{"table_name": []}}` to select ALL columns of a table
- Use `{empty_json}` to select ALL tables and ALL columns
- Use `{{"__no_db__": true}}` for greetings/thanks/farewells, or for tasks that summarize/explain existing results without needing new data.

Please output ONLY the JSON inside a ```json code block. Do NOT output raw JSON without the code block. Do not add any explanation before or after the code block:

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
{empty_json}
```

No database query needed (only for pure conversation):
```json
{{
    "__no_db__": true
}}
```"""


def filter_db_fields(question, engine, llm, tables=None, retries=2):
    for attempt in range(retries):
        response = call_with_context_retry(lambda lvl: _build_filter_prompt(question, engine, tables, level=lvl), llm)
        result = parse_selected_fields_json(response.content)
        if result is not None and isinstance(result, dict):
            logging.info(f"filter_db_fields: Question: {question}\nResult: {result}\n")
            return result
        print(f"filter_db_fields parse failed (attempt {attempt+1}), raw: {response.content[:200]}")

    return None


def filter_db_fields_stream(question, engine, llm, tables=None):
    yield {"type": "status", "content": "Analyzing database structure..."}
    yield {"type": "status", "content": "Filtering relevant tables and fields..."}

    prompt = _build_filter_prompt(question, engine, tables)
    prompt_length = len(prompt)
    full_content = ""

    for chunk, _ in stream_with_context_retry(lambda lvl: _build_filter_prompt(question, engine, tables, level=lvl), llm):
        full_content += chunk
        yield {"type": "chunk", "content": chunk}

    result = parse_selected_fields_json(full_content)
    if result is not None and isinstance(result, dict):
        logging.info(f"filter_db_fields_stream: Question: {question}\nResult: {result}\n")
        yield {"type": "done", "content": full_content, "selected_fields": result, "prompt_length": prompt_length}
    else:
        yield {"type": "error", "content": "Field filtering parsing failed", "selected_fields": None, "prompt_length": prompt_length}
