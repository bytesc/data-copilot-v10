import pandas as pd
import sqlalchemy

from agent.utils.get_config import config_data
from agent.utils.llm_access.LLM import get_llm
from .copilot.data_explanation import get_llm_data_explanation_func
from .copilot.examples.path_tools import generate_img_path
from .copilot.utils.read_db import execute_select
from .data_trans.download_csv_to_pd import download_csv_to_dataframe, extract_csv_filename_from_url, read_csv_from_local
from .copilot.sql_code import query_database_func
from .copilot.python_code import draw_graph_func, draw_compare_graph_func
from .web_search.web_search import search_web, fetch_webpage


DATABASE_URL = config_data['mysql']
engine = sqlalchemy.create_engine(DATABASE_URL)

STATIC_URL = config_data['static_path']

llm = get_llm()




def query_database(question: str, df_cols: str | list = None) -> pd.DataFrame:
    """
    query_database(question: str, df_cols: str | list = None) -> pd.DataFrame:
    Query the database using natural language question. Can not query anything not included in the database content!!!
    Returns the query results in pandas DataFrame.

    Args:
    - question (str): Natural language question, table names can be included in the question.
    - df_cols (str|list): The columns' names of the DataFrame(e.g. "uid, username, stu_num").

    Returns:
    - pd.DataFrame: A DataFrame containing the results of the database query.
        The DataFrame includes the columns provided in df_cols(the second args)
    returns None in case of error

    Example:
    ```python
        ans_df = query_database('Select the grades of Jane Smith, use table stu_grade ,stu_info, class_info', df_cols='lesson_id, lesson_name, grade')
        # Output(pd.DataFrame):
        #        lesson_id lesson_name grade
        # 0        001  Mathematics     99.00
        # 1        002      English     88.50
        # 2        003     Physics    65.00
        # ... and so on(the structure of the output DataFrame id based on df_cols(the second input args))
    ```
    """

    result = query_database_func(question, df_cols, llm, engine)
    return result


def draw_graph(question: str, data: pd.DataFrame, col_explanation: str = None) -> str:
    """
    draw_graph(question: str, data: pd.DataFrame, col_explanation: str = None) -> str:
    Draw graph based on natural language graph description and data provided in a pandas DataFrame.
    Returns an url path string of the graph.

    Args:
    - question (str): Natural language graph type and other requirements.
    - data (pd.DataFrame): A pandas DataFrame for providing drawing data.
    - col_explanation (str, optional): Natural language to describe the meanings of columns.

    Returns:
    - str: url path string of the output graph.(e.g. "http://127.0.0.1:8003/tmp_imgs/mlkjcvep.png").
    returns None in case of error

    Example:
    ```python
        data = pd.DataFrame({
            '月份': ['1月', '2月', '3月', '4月', '5月'],
            '销售额': [200, 220, 250, 210, 230]
        })
        graph_url = draw_graph("draw line graph, use red line", data)
        # Output(str):
        # "http://127.0.0.1:8003/tmp_imgs/ekhidpcl.png"

        data = pd.DataFrame({
            'Gender': [1, 2, 3],
            'Sales Percentage': [35, 45, 20]
        })
        graph_url = draw_graph("draw pie chart", data, "Gender: 1 means male, 2 means female, 3 means not known;")
        # Output(str):
        # "http://127.0.0.1:8003/tmp_imgs/ewcdkdkl.png"

        data = pd.DataFrame({
            'Month': ['January', 'February', 'March', 'April', 'May', 'June'],
            'Sales Revenue (USD)': [12000, 15000, 18000, 13500, 16500, 19500]
        })
        graph_url = draw_graph("draw bar chart, use different color for each bar", data)
        # Output(str):
        # "http://127.0.0.1:8003/tmp_imgs/glddvysc.png"
    ```
    """
    result = draw_graph_func(question, data, llm, col_explanation)
    result = STATIC_URL + result[2:]
    return result


def draw_compare_graph(question: str, data_dict: dict, col_explanation: str = None) -> str:
    """
    draw_compare_graph(question: str, data_dict: dict, col_explanation: str = None) -> str:
    Draw graph to compare something based on natural language graph description and data provided in a dictionary of pandas DataFrames.
    Returns an url path string of the graph.

    Args:
    - question (str): Natural language graph type and other requirements.
    - data_dict (dict): A dictionary with string keys and pandas DataFrame values for providing drawing data. The key can only be a string and the value can only be a pandas DataFrame.
    - col_explanation (str, optional): Natural language to describe the meanings of columns.

    Returns:
    - str: url path string of the output graph.(e.g. "http://127.0.0.1:8003/tmp_imgs/mlkjcvep.png").
    returns None in case of error

    Example:
    ```python
        data_dict = {
            'sales_data': pd.DataFrame({
                '月份': ['1月', '2月', '3月', '4月', '5月'],
                '销售额': [200, 220, 250, 210, 230]
            }),
            'inventory_data': pd.DataFrame({
                '月份': ['1月', '2月', '3月', '4月', '5月'],
                '库存量': [100, 90, 80, 95, 85]
            })
        }
        graph_url = draw_compare_graph("draw line graph", data_dict)
        # Output(str):
        # "http://127.0.0.1:8003/tmp_imgs/ekhidpcl.png"

        data_dict = {
            'group A': pd.DataFrame({
                'Gender': [1, 2, 3],
                'Sales Percentage': [35, 45, 20]
            }),
            'group B': pd.DataFrame({
                'Gender': [1, 2, 3],
                'Sales Percentage': [31, 59, 3]
            })
        }
        graph_url = draw_compare_graph("draw pie chart", data_dict, "use blend bar layers to compare two groups. Gender: 1 means male, 2 means female, 3 means not known;")
        # Output(str):
        # "http://127.0.0.1:8003/tmp_imgs/ewcdkdkl.png"

        data_dict = {
            'monthly_sales': pd.DataFrame({
                'Month': ['January', 'February', 'March', 'April', 'May', 'June'],
                'Sales Revenue (USD)': [12000, 15000, 18000, 13500, 16500, 19500]
            })
        }
        graph_url = draw_compare_graph("draw bar chart, use different color for each bar", data_dict)
        # Output(str):
        # "http://127.0.0.1:8003/tmp_imgs/glddvysc.png"
    ```
    """
    result = draw_compare_graph_func(question, data_dict, llm, col_explanation)
    result = STATIC_URL + result[2:]
    return result


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
    returns None in case of error

    Example:
    ```python
        ans_df = exe_sql('SELECT lesson_id, lesson_name, grade FROM lessons WHERE grade > 90')
        # Output(pd.DataFrame):
        #        lesson_id lesson_name grade
        # 0        001  Mathematics     99.00
        # 1        002      English     95.50
        # 2        005     Chemistry     92.00
        # ... and so on
        ```
    """
    ans = execute_select(engine, sql)
    return ans


def load_data(url: str) -> pd.DataFrame:
    """
    load_data(url: str) -> pd.DataFrame:
    Load data form a CSV file url. You can use it to retrieve the data queried or processed in the context.
    Returns the result in a pandas DataFrame.

    Args:
    - url (str): url string(e.g. http://127.0.0.1:8009/tmp_imgs/imqtzywu.csv).

    Returns:
    - pd.DataFrame: A DataFrame containing the data in the CSV file.
    returns None in case of error

    Example:
    ```python
        ans_df = load_data("http://127.0.0.1:8009/tmp_imgs/xjfsutvp.csv")
    ```
    """
    file_name = extract_csv_filename_from_url(url)
    df = read_csv_from_local("./tmp_imgs/"+file_name)
    return df


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
            import pandas as pd
            import math
            import numpy as np
            import PIL
            import matplotlib
            import matplotlib.pyplot as plt
            plt.rcParams['font.family'] = 'SimHei'

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
