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
    return f"""你是一个数据库分析助手。用户提出了以下问题：

"{question}"

下面是数据库中所有表的结构和注释信息：

{schema}

请根据用户的问题，筛选出回答该问题需要用到的数据库表和字段。

要求：
1. 只选择与问题直接相关的表和字段
2. 如果某个表的所有字段都不相关，不要包含该表
3. 如果某个表只有部分字段相关，只包含那些相关的字段
4. 必须包含用于表关联的关键字段（如外键、ID等）
5. 输出格式为 JSON，key 为表名，value 为需要使用的字段名列表

请严格按照以下 JSON 格式输出，不要添加任何其他解释或说明：

```json
{{
    "table_name_1": ["column_a", "column_b", "id"],
    "table_name_2": ["id", "name"]
}}
```

如果判断用户的问题不需要查询数据库，请输出空对象：

```json
{{}}
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
