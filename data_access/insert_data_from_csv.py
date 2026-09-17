import io
import re

from data_access.read_db import execute_sql, execute_select
from data_access.db_conn import engine
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, MetaData, Table, Column, text, inspect
from sqlalchemy.types import VARCHAR, Integer, Float, DateTime, Boolean, Text
from datetime import datetime


def sanitize_column_name(name: str, used_names: set) -> str:
    cleaned = re.sub(r'[^\w]', '_', str(name))
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')
    if not cleaned or cleaned[0].isdigit():
        cleaned = 'col_' + cleaned
    if not cleaned:
        cleaned = 'column'
    while cleaned in used_names or cleaned.lower() in {
        'select', 'insert', 'update', 'delete', 'drop', 'alter', 'create',
        'table', 'where', 'from', 'and', 'or', 'not', 'null', 'true', 'false',
        'order', 'group', 'by', 'having', 'join', 'union', 'into', 'values',
        'set', 'distinct', 'as', 'exists', 'between', 'like', 'in', 'is',
        'primary', 'key', 'index', 'constraint', 'default', 'check', 'foreign',
        'references', 'add', 'column', 'modify', 'change', 'rename', 'analyze',
        'use', 'show', 'describe', 'explain', 'grant', 'revoke', 'lock',
        'unlock', 'execute', 'call', 'begin', 'commit', 'rollback',
    }:
        cleaned += '_'
    used_names.add(cleaned)
    return cleaned


def pandas_type_to_sqlalchemy(dtype, max_length=None):
    if pd.api.types.is_integer_dtype(dtype):
        return Integer()
    elif pd.api.types.is_float_dtype(dtype):
        return Float()
    elif pd.api.types.is_datetime64_any_dtype(dtype):
        return DateTime()
    elif pd.api.types.is_bool_dtype(dtype):
        return Boolean()
    else:
        if max_length is not None and max_length <= 500:
            return VARCHAR(max_length)
        else:
            return Text()


def sanitize_table_name(name: str) -> str:
    cleaned = re.sub(r'[^\w]', '_', str(name))
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')
    if not cleaned or cleaned[0].isdigit():
        cleaned = 'tbl_' + cleaned
    if not cleaned:
        cleaned = 'uploaded_data'
    return cleaned.lower()


def process_csv_to_database(file_content: bytes, table_name: str = "uploaded_data"):
    try:
        df = pd.read_csv(io.BytesIO(file_content))
        table_name = sanitize_table_name(table_name)
        used = set()
        rename_map = {col: sanitize_column_name(col, used) for col in df.columns}
        df.rename(columns=rename_map, inplace=True)
        inspector = inspect(engine)
        if inspector.has_table(table_name):
            with engine.connect() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS `{table_name}`"))
                conn.commit()
        column_types = {}
        for col in df.columns:
            col_data = df[col]
            col_data_not_null = col_data.dropna()
            if len(col_data_not_null) == 0:
                column_types[col] = VARCHAR(255)
                continue

            max_length = None
            if col_data.dtype == 'object':
                try:
                    max_length = int(col_data_not_null.astype(str).str.len().max())
                    max_length = min(max_length * 2, 8000)
                except:
                    max_length = 255

            column_types[col] = pandas_type_to_sqlalchemy(col_data.dtype, max_length)

        try:
            df.to_sql(
                name=table_name,
                con=engine,
                index=False,
                dtype=column_types
            )
            result_msg = f"Successfully created table '{table_name}' and inserted {len(df)} records."
            print(result_msg)

            return {
                "type": "success",
                "message": result_msg,
                "row_count": len(df),
                "table_name": table_name
            }
        except Exception as e:
            print(str(e))
            return {
                "type": "error",
                "message": str(e),
                "row_count": 0,
                "table_name": table_name
            }
    except Exception as e:
        print(str(e))
        return {
            "type": "error",
            "message": str(e),
            "row_count": 0,
            "table_name": table_name
        }
