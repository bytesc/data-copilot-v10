from .tools.copilot.sql_code import get_db_info_prompt
from .tools.copilot.utils.parse_output import parse_generated_sql_code
from .tools.copilot.utils.read_db import execute_sql, execute_sql_2, execute_sql_3
from .tools.tools_def import engine, llm
from utils.context_trim import call_with_context_retry, cap_text

def get_llm_data_comment_func(txt, table):
    print("##############doc")
    print(txt)
    data_str = get_db_info_prompt(engine, simple=True, example=False, tables=[table])

    pre_prompt = """
Please write sql code to add table and colum comments to the table.
Here is the document:
"""

    data_prompt = """
Here is the table structure: 
""" + data_str + """
only write comment for the specified  table name: 
""" + table

    end_prompt = """
Reminders:
1. All code must be completed in a single markdown code block without any comments, explanations, or commands.
2. Use MySQL 5.7 dialect.
3. Comments should be short and clear. Column comments should be no more than 20 words. Table comments should be no more than 100 words.
4. When generating MySQL ALTER TABLE statements to add COMMENT to columns, if the comment text contains a single quote ', it MUST be escaped as two single quotes '', otherwise it will cause a 1064 syntax error.

Example:
- Incorrect: COMMENT 'It''s an example (e.g. '1000')'
- Correct: COMMENT 'It''s an example (e.g. ''1000'')'

IMPORTANT: You MUST ONLY generate comments for the table specified in the table structure above. Do NOT include any other tables in your output. Focus exclusively on the table named in the schema information provided.
"""

    def build_prompt(level):
        return pre_prompt + cap_text(txt, level) + "\n" + "Here is the table structure: \n" + cap_text(data_str, level) + """
only write comment for the specified  table name: 
""" + table + "\n" + end_prompt

    ans = call_with_context_retry(build_prompt, llm)
    print("##############sql")
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
        print(str(ans.content) + "No code was generated.")

    return result_sql


def get_llm_data_comment(extracted_text, table_name):
    sql = get_llm_data_comment_func(extracted_text, table_name)
    if not sql or not str(sql).strip():
        print("[WARNING] No SQL comment statements were generated; skipping comment update.")
        return False
    execute_sql_3(engine, sql)
    return True
