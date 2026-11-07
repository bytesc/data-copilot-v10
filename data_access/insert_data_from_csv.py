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


def _create_table_from_df(df, table_name, column_types):
    inspector = inspect(engine)
    if inspector.has_table(table_name):
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{table_name}`"))
            conn.commit()
    df.iloc[:0].to_sql(name=table_name, con=engine, index=False, dtype=column_types)


def _insert_rows_bulk(df, table_name):
    df.to_sql(name=table_name, con=engine, index=False, if_exists='append')


# Cap the number of reported validation errors so a large broken CSV cannot
# produce an unbounded error string that is then returned to the client.
_MAX_VALIDATION_ERRORS = 100


def _validate_rows(df, column_types, max_errors=_MAX_VALIDATION_ERRORS):
    """Validate column types with vectorized per-column checks.

    The previous implementation iterated every cell with ``df.iloc[i][col]``,
    which builds a whole Series per row (O(rows * columns) Series allocations)
    and was very slow on large uploads. Each dtype is now checked once with a
    vectorized mask over the entire column.
    """
    errors = []
    row_count = len(df)

    for col in df.columns:
        dtype = column_types[col]
        series = df[col]
        not_null = series.notna()
        if not not_null.any():
            continue

        message = None
        max_len = None

        if isinstance(dtype, Integer):
            mask = not_null & pd.to_numeric(series, errors="coerce").isna()
            message = "Cannot convert to integer"
        elif isinstance(dtype, Float):
            mask = not_null & pd.to_numeric(series, errors="coerce").isna()
            message = "Cannot convert to number"
        elif isinstance(dtype, DateTime):
            mask = not_null & pd.to_datetime(series, errors="coerce").isna()
            message = "Cannot convert to datetime"
        elif isinstance(dtype, Boolean):
            allowed = ("true", "false", "1", "0", "yes", "no")
            normalized = series.astype(str).str.strip().str.lower()
            mask = not_null & ~normalized.isin(allowed)
            message = "Cannot convert to boolean"
        elif isinstance(dtype, VARCHAR):
            max_len = dtype.length
            mask = not_null & (series.astype(str).str.len() > max_len)
        else:
            continue

        for i in np.flatnonzero(mask.to_numpy()):
            if len(errors) >= max_errors:
                errors.append(
                    f"... more validation errors omitted ({row_count} rows checked)"
                )
                return errors
            i = int(i)
            value = series.iat[i]
            if max_len is not None:
                errors.append(
                    f"Row {i + 2}, column '{col}': Value too long "
                    f"({len(str(value))} chars, max {max_len})"
                )
            else:
                errors.append(
                    f"Row {i + 2}, column '{col}': {message} (value: {value!r})"
                )

    return errors


def process_csv_to_database(file_content: bytes, table_name: str = "uploaded_data"):
    try:
        df = pd.read_csv(io.BytesIO(file_content))
        table_name = sanitize_table_name(table_name)
        used = set()
        rename_map = {col: sanitize_column_name(col, used) for col in df.columns}
        df.rename(columns=rename_map, inplace=True)

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

        validation_errors = _validate_rows(df, column_types)
        if validation_errors:
            return {
                "success": False,
                "error": "Validation failed:\n" + "\n".join(validation_errors),
                "row_count": 0,
                "table_name": table_name
            }

        _create_table_from_df(df, table_name, column_types)
        _insert_rows_bulk(df, table_name)
        result_msg = f"Successfully created table '{table_name}' and inserted {len(df)} records."
        print(result_msg)
        return {
            "success": True,
            "message": result_msg,
            "row_count": len(df),
            "table_name": table_name
        }

    except Exception as e:
        err_msg = str(e)
        print(err_msg)
        return {
            "success": False,
            "error": f"Import failed. The DB reports: {err_msg}",
            "row_count": 0,
            "table_name": table_name
        }