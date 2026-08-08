from datetime import datetime
from sqlalchemy import (
    Table, Column, Integer, String, Text, DateTime, MetaData, insert
)

from data_access.sys_db_conn import sys_engine

metadata = MetaData()

session_operation_log = Table(
    "session_operation_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(255), nullable=False, comment="会话ID"),
    Column("api_endpoint", String(255), nullable=False, comment="调用的API接口"),
    Column("question", Text, comment="用户输入的问题"),
    Column("ans", Text, comment="返回的结果"),
    Column("code", Text, comment="生成的代码"),
    Column("result_type", String(50), comment="success/error"),
    Column("msg", String(512), comment="处理结果描述"),
    Column("prompt_length", Integer, comment="prompt长度"),
    Column("created_at", DateTime, comment="记录时间"),
)


def create_session_log_table():
    metadata.create_all(sys_engine)


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
