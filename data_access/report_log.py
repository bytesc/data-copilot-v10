from datetime import datetime
from sqlalchemy import (
    Table, Column, Integer, String, Text, DateTime, MetaData, insert
)
from sqlalchemy.dialects.mysql import LONGTEXT

from data_access.sys_db_conn import sys_engine

metadata = MetaData()

report_generation_log = Table(
    "report_generation_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(255), nullable=False, comment="会话ID"),
    Column("file_name", String(512), comment="生成的文件名"),
    Column("chat_history", LONGTEXT, comment="输入的聊天历史(JSON)"),
    Column("outline", LONGTEXT, comment="生成的大纲"),
    Column("full_text", LONGTEXT, comment="生成的全文"),
    Column("created_at", DateTime, comment="记录时间"),
)


def create_report_log_table():
    metadata.create_all(sys_engine)


def record_report_generation(session_id, file_name, chat_history="", outline="", full_text=""):
    if not session_id:
        return
    try:
        with sys_engine.connect() as conn:
            conn.execute(
                insert(report_generation_log).values(
                    session_id=session_id,
                    file_name=file_name,
                    chat_history=chat_history,
                    outline=outline,
                    full_text=full_text,
                    created_at=datetime.now(),
                )
            )
            conn.commit()
    except Exception as e:
        print(f"记录报告生成日志失败: {e}")