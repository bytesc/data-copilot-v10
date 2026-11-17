import json
from datetime import datetime

from sqlalchemy import (
    Table, Column, Integer, String, Boolean, DateTime, MetaData, insert
)
from sqlalchemy.dialects.mysql import LONGTEXT

from config.get_config import config_data
from data_access.sys_db_conn import sys_engine


metadata = MetaData()

web_access_log = Table(
    "web_access_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(255), comment="会话ID（可能为空）"),
    Column("access_type", String(50), comment="行为类型：web_search / fetch_webpage"),
    Column("query", LONGTEXT, comment="搜索关键词（web_search）"),
    Column("urls", LONGTEXT, comment="抓取的URL列表(JSON数组，fetch_webpage)"),
    Column("success", Boolean, comment="是否成功"),
    Column("error", String(1024), comment="失败原因"),
    Column("duration_ms", Integer, comment="本次访问耗时(ms)"),
    Column("result", LONGTEXT, comment="返回结果(JSON字符串)"),
    Column("created_at", DateTime, index=True, comment="记录时间"),
)


def create_web_access_log_table():
    if sys_engine is None:
        return
    metadata.create_all(sys_engine)


def record_web_access(session_id=None, access_type="", query="", urls=None,
                      success=True, error="", duration_ms=None, result=""):
    """Record one web_search / fetch_webpage call.

    Best-effort: never raises into the tool path. ``urls`` may be a list (stored
    as a JSON array string) or an already-serialized string. ``result`` is stored
    verbatim and is expected to be the raw JSON string returned by the tool.
    """
    if sys_engine is None or not config_data.get("enable_web_access_log", True):
        return
    try:
        if urls is not None and not isinstance(urls, str):
            urls = json.dumps(urls, ensure_ascii=False)
    except (TypeError, ValueError):
        urls = ""
    try:
        with sys_engine.connect() as conn:
            conn.execute(
                insert(web_access_log).values(
                    session_id=session_id or None,
                    access_type=access_type or "",
                    query=query or "",
                    urls=urls or "",
                    success=bool(success),
                    error=(error or "")[:1024],
                    duration_ms=duration_ms,
                    result=result or "",
                    created_at=datetime.now(),
                )
            )
            conn.commit()
    except Exception as e:
        print(f"记录Web访问日志失败: {e}")
