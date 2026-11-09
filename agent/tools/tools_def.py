import json

import pandas as pd
import sqlalchemy

from agent.utils.get_config import config_data
from agent.utils.llm_access.LLM import get_llm_dynamic
# Reuse the single user-database engine defined in ``data_access.db_conn`` so the
# project does not open two independent connection pools (each 20+20) against the
# same database, which doubled connections and split the transaction view.
from data_access.db_conn import engine
from .copilot.data_explanation import get_llm_data_explanation_func
from .copilot.examples.path_tools import generate_img_path
from .copilot.utils.read_db import execute_select
from .data_trans.download_csv_to_pd import download_csv_to_dataframe, extract_csv_filename_from_url, read_csv_from_local
from .web_search.web_search import search_web, fetch_webpage
from .mcp_client import load_mcp_servers, get_mcp_server, MCPClient, MCPError

from .copilot.utils.mpl_chinese_font import setup_chinese_font
setup_chinese_font()


# exe_sql uses the read-only user to run SELECT/SHOW. Mutating features keep using engine
# (the first user). When mysql_readonly is not configured, read-only queries are disabled
# rather than silently falling back to the privileged user: the SQL-text validation was
# removed, so the read-only account is now the only access control for these queries.
READONLY_DATABASE_URL = config_data.get('mysql_readonly') or ""
if READONLY_DATABASE_URL:
    read_engine = sqlalchemy.create_engine(
        READONLY_DATABASE_URL,
        pool_size=20,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
else:
    read_engine = None
    print(
        "[WARNING] mysql_readonly is not configured; read-only queries (exe_sql) "
        "are disabled. A privileged fallback is intentionally not used."
    )

STATIC_URL = config_data['static_path']
STATIC_FOLDER = "tmp_imgs"

llm = get_llm_dynamic()




def explain_data(question: str, data: pd.DataFrame, col_explanation: str = None) -> str:
    """
    explain_data(question: str, data: pd.DataFrame, col_explanation: str = None) -> str:
    Explain the data provided in a pandas DataFrame based on a natural language question. This function must be used after important dataframe assigned.
    Returns a str of natural language data analysis.

    Args:
    - question (str): Natural language question.
    - data (pd.DataFrame): A pandas DataFrame for analysis.
    - col_explanation (str, optional): Natural language to describe the meanings of columns.

    Returns:
    - str: Explanation of data

    Example:
    ```python
        data = pd.DataFrame({
            'month': ['1', '2', '3', '4', '5'],
            'sales': [200, 220, 250, 210, 230]
        })
        data_description = explain_data("how is the sales condition?", data, "month: 1 means Jan and so forth")
        # Output(str):
        # "Based on the data..."
    ```
    """
    ans = get_llm_data_explanation_func(question, data, llm, col_explanation)
    return ans


def exe_sql(sql: str) -> pd.DataFrame:
    """
    exe_sql(sql: str) -> pd.DataFrame:
    Execute the sql query string. Must be used in case of data query with sql database.
    Returns the query results in pandas DataFrame.

    Args:
    - sql (str): query string.

    Returns:
    - pd.DataFrame: A DataFrame containing the results of the database query.
      The result may still be EMPTY (0 rows), so always keep checking
      `df is None or df.empty` after the call and handle that case.

    Raises:
    - RuntimeError: If no read-only database is configured (mysql_readonly missing).
    - Exception: If the SQL statement fails (syntax error, unknown table/column,
      timeout, ...). This function does NOT return None on error; the runtime
      catches the exception and regenerates the code with the error message,
      so you do NOT need to wrap this call in try/except.

    Example:
    ```python
        ans_df = exe_sql('SELECT lesson_id, lesson_name, grade FROM lessons WHERE grade > 90')
        # Output(pd.DataFrame):
        #        lesson_id lesson_name grade
        # 0        001  Mathematics     99.00
        # 1        002      English     95.50
        # 2        005     Chemistry     92.00
        # ... and so on
        if ans_df is None or ans_df.empty:
            yield "No matching records were found in the database"
            return
        ```
    """
    ans = execute_select(read_engine, sql)
    return ans


def load_data(url: str) -> pd.DataFrame:
    """
    load_data(url: str) -> pd.DataFrame:
    Load data form a CSV file url. You can use it to retrieve the data queried or processed in the context.
    Returns the result in a pandas DataFrame.

    Args:
    - url (str): url string(e.g. "./tmp_imgs/imqtzywu.csv").

    Returns:
    - pd.DataFrame: A DataFrame containing the data in the CSV file.
    returns None in case of error

    Example:
    ```python
        ans_df = load_data("./tmp_imgs/xjfsutvp.csv")
    ```
    """
    file_name = extract_csv_filename_from_url(url)
    if not file_name:
        return None
    df = read_csv_from_local(f"./{STATIC_FOLDER}/"+file_name)
    return df


def exe_mcp(server: str, tool: str, params: dict = None) -> str:
    """
    exe_mcp(server: str, tool: str, params: dict = None) -> str:
    Execute a tool on an MCP (Model Context Protocol) server. Use this to call external capabilities like sending emails, querying external APIs, or accessing specialized services.
    Returns the tool execution result as a formatted string.

    Args:
    - server (str): The MCP server name (e.g. "calculator", "email", "weather").
    - tool (str): The tool name to execute on the server.
    - params (dict, optional): Parameters to pass to the tool.

    Returns:
    - str: Formatted result text from the MCP tool execution.
    returns error message string in case of error

    Example:
    ```python
        result = exe_mcp("calculator", "calculate", {"expression": "2 + 2"})
        # Output(str):
        # "### calculator/calculate\n\n4"
    ```
    """
    server_config = get_mcp_server(server)
    if not server_config:
        return f"Error: MCP server not found: {server}"

    try:
        with MCPClient(server_config) as client:
            result = client.call_tool(tool, params or {})
    except MCPError as e:
        return f"Error: MCP call failed - {server}/{tool}: {e}"
    except Exception as e:
        return f"Error: MCP call failed - {server}/{tool}: {e}"

    result_content = result.get("content", [])
    result_text_parts = []
    for part in result_content:
        if isinstance(part, dict):
            if part.get("type") == "text":
                result_text_parts.append(part.get("text", ""))
            elif part.get("type") == "resource":
                resource = part.get("resource", {})
                result_text_parts.append(f"[Resource] {resource.get('text', '')}")
        else:
            result_text_parts.append(str(part))
    result_text = "\n".join(result_text_parts) if result_text_parts else json.dumps(result, ensure_ascii=False, indent=2)

    combined = f"### {server}/{tool}\n\n{result_text}"
    return combined


def get_save_image_path() -> str:
    """
       get_save_image_path() -> str:
       get the path to save the generated graph image, you can only save it in the generated path, not anywhere else. Must be used in case of drawing plots.
       Returns str path to save the png image, the path include the `.png` file name.

       Returns:
       - str: A unique path to save the png graph image, the path include the file name.
       Example:
       ```python
        def func(data_dict):
import json
import pandas as pd
            import math
            import numpy as np
            import PIL
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from agent.tools.copilot.utils.mpl_chinese_font import setup_chinese_font
            setup_chinese_font()

            # Data
            x = data_dict['x']
            y1 = data_dict['y1']
            y2 = data_dict['y2']

            # Plot
            fig, ax = plt.subplots(figsize=(8, 5))
            ax.bar(x, y1, label='A', color='steelblue')
            ax.bar(x, y2, bottom=y1, label='B', color='coral')

            ax.set_xlabel('Month')
            ax.set_ylabel('Sales')
            ax.set_title('Monthly Sales Comparison')
            ax.legend()

            # Get path to save the image
            path = get_save_image_path()
            # (e.g. ./tmp_imgs/imqtzywu.png) just an example, get_save_image_path() generates different ramdom path each time.
            # save the graph image
            plt.savefig(path)
            plt.close()

            return path
       ```
       """
    return generate_img_path()
