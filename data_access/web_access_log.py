import json
from datetime import datetime

from sqlalchemy import (
    Table, Column, Integer, String, Boolean, DateTime, MetaData, insert, select, desc
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


def _serialize_row(row_dict):
    return {
        k: v.isoformat() if isinstance(v, datetime) else v
        for k, v in row_dict.items()
    }


def list_web_access_logs(limit=100, access_type=None, session_id=None):
    """List web_search / fetch_webpage records, newest first.

    The heavy ``result`` column is intentionally excluded; fetch a single
    record with :func:`get_web_access_log` when the full payload is needed.
    """
    if sys_engine is None:
        return []
    try:
        with sys_engine.connect() as conn:
            query = select(
                web_access_log.c.id,
                web_access_log.c.session_id,
                web_access_log.c.access_type,
                web_access_log.c.query,
                web_access_log.c.urls,
                web_access_log.c.success,
                web_access_log.c.error,
                web_access_log.c.duration_ms,
                web_access_log.c.created_at,
            )
            if access_type:
                query = query.where(web_access_log.c.access_type == access_type)
            if session_id:
                query = query.where(web_access_log.c.session_id == session_id)
            result = conn.execute(
                query.order_by(desc(web_access_log.c.created_at)).limit(limit)
            ).fetchall()
            return [_serialize_row(dict(row._mapping)) for row in result]
    except Exception as e:
        print(f"查询Web访问日志失败: {e}")
        return []


def get_web_access_log(log_id):
    """Return one full web access record (including ``result``) or ``None``."""
    if sys_engine is None:
        return None
    try:
        with sys_engine.connect() as conn:
            row = conn.execute(
                select(web_access_log).where(web_access_log.c.id == log_id)
            ).fetchone()
            if row is None:
                return None
            return _serialize_row(dict(row._mapping))
    except Exception as e:
        print(f"查询Web访问日志详情失败: {e}")
        return None
