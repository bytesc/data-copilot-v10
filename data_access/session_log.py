from datetime import datetime
from sqlalchemy import (
    Table, Column, Integer, String, DateTime, MetaData, insert
)
from sqlalchemy.dialects.mysql import LONGTEXT

from data_access.sys_db_conn import sys_engine

metadata = MetaData()

session_operation_log = Table(
    "session_operation_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(255), nullable=False, comment="会话ID"),
    Column("api_endpoint", String(255), nullable=False, comment="调用的API接口"),
    Column("question", LONGTEXT, comment="用户输入的问题"),
    Column("ans", LONGTEXT, comment="返回的结果"),
    Column("code", LONGTEXT, comment="生成的代码"),
    Column("result_type", String(50), comment="success/error"),
    Column("msg", String(512), comment="处理结果描述"),
    Column("prompt_length", Integer, comment="prompt长度"),
    Column("created_at", DateTime, comment="记录时间"),
)


def create_session_log_table():
    metadata.create_all(sys_engine)
    _ensure_column_exists(sys_engine, "session_operation_log", "question", "LONGTEXT COMMENT 'question'")
    _ensure_column_exists(sys_engine, "session_operation_log", "ans", "LONGTEXT COMMENT 'ans'")
    _ensure_column_exists(sys_engine, "session_operation_log", "code", "LONGTEXT COMMENT 'code'")


def _ensure_column_exists(engine, table_name, column_name, column_def):
    import pymysql
    url = engine.url
    try:
        conn = pymysql.connect(
            host=url.host, port=url.port, user=url.username,
            password=url.password, database=url.database
        )
        cursor = conn.cursor()
        cursor.execute(f"SHOW COLUMNS FROM {table_name} LIKE '{column_name}'")
        row = cursor.fetchone()
        if not row:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
        else:
            current_type = (row[1] or "").upper()
            target_type = column_def.split()[0].upper()
            if current_type != target_type:
                cursor.execute(f"ALTER TABLE {table_name} MODIFY COLUMN {column_name} {column_def}")
        conn.commit()
        conn.close()
    except Exception:
        pass


def record_session_operation(
    session_id,
    api_endpoint,
    question,
    ans="",
    code="",
    result_type="",
    msg="",
    prompt_length=0,
):
    if not session_id:
        return
    try:
        with sys_engine.connect() as conn:
            conn.execute(
                insert(session_operation_log).values(
                    session_id=session_id,
                    api_endpoint=api_endpoint,
                    question=question,
                    ans=ans,
                    code=code,
                    result_type=result_type,
                    msg=msg,
                    prompt_length=prompt_length,
                    created_at=datetime.now(),
                )
            )
            conn.commit()
    except Exception as e:
        print(f"记录session操作日志失败: {e}")
