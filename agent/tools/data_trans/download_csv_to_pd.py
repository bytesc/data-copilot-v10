import re

import pandas as pd
import requests
from io import StringIO


def download_csv_to_dataframe(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        content = response.content.decode('utf-8')
        df = pd.read_csv(StringIO(content))
        return df

    except requests.exceptions.RequestException as e:
        print(f"下载失败: {e}")
        return None
    except Exception as e:
        print(f"处理CSV数据时发生错误: {e}")
        return None


def read_csv_from_local(file_path):
    try:
        df = pd.read_csv(file_path)
        return df
    except Exception as e:
        print(f"读取文件失败: {e}")
        return None


def extract_csv_filename_from_url(url):
    match = re.search(r'/([^/]+\.csv)$', url, re.IGNORECASE)
    if not match:
        return None
    # Reject traversal outright rather than rewriting it: the regex above
    # only excludes "/", so on Windows a name like "..\\..\\secret.csv"
    # would otherwise be joined to tmp_imgs and escape it. The filenames
    # load_data itself produces are 8 random lowercase letters, so no
    # legitimate name contains ".." or a backslash.
    file_name = match.group(1)
    if ".." in file_name or "\\" in file_name:
        return None
    return file_name


if __name__ == "__main__":

    url = "./tmp_imgs/givtimqtzywu.csv"
    print(extract_csv_filename_from_url(url))
    df = download_csv_to_dataframe(url)

    if df is not None:
        print(f"DataFrame形状: {df.shape}")
        print(df.head())
    else:
        print("下载失败")
