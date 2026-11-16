import json
from datetime import datetime, timedelta

from sqlalchemy import (
    Table, Column, Integer, String, DateTime, MetaData, insert, select, func
)
from sqlalchemy.dialects.mysql import LONGTEXT

from config.get_config import config_data
from data_access.sys_db_conn import sys_engine


metadata = MetaData()

llm_log = Table(
    "llm_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(255), comment="会话ID（可能为空）"),
    Column("input", LONGTEXT, comment="输入消息(JSON字符串，已去除图片base64)"),
    Column("output", LONGTEXT, comment="输出文本"),
    Column("prompt_tokens", Integer, comment="prompt token数"),
    Column("completion_tokens", Integer, comment="completion token数"),
    Column("total_tokens", Integer, comment="总token数"),
    Column("reasoning_tokens", Integer, comment="reasoning token数"),
    Column("first_token_ms", Integer, comment="首字符响应延迟(ms)，非流式为NULL"),
    Column("duration_ms", Integer, comment="本次调用总耗时(ms)"),
    Column("created_at", DateTime, index=True, comment="记录时间"),
)

# Index on created_at (auto name "ix_llm_log_created_at") so the sliding-window
# token sum for the TPH limit does not full-scan this large LONGTEXT table.
_CREATED_AT_INDEX = "ix_llm_log_created_at"

# Sliding window length for the token-per-hour limit.
TPH_WINDOW_MINUTES = 60


def create_llm_log_table():
    if sys_engine is None:
        return
    metadata.create_all(sys_engine)
    _ensure_created_at_index()


def _ensure_created_at_index():
    """Add the created_at index to an already-existing llm_log table.

    ``metadata.create_all`` only creates the index on a fresh table; it does not
    alter a table that already exists, so deploy the index explicitly. Idempotent.
    """
    import pymysql
    url = sys_engine.url
    try:
        conn = pymysql.connect(
            host=url.host, port=url.port, user=url.username,
            password=url.password, database=url.database
        )
        cursor = conn.cursor()
        cursor.execute(f"SHOW INDEX FROM llm_log WHERE Key_name = '{_CREATED_AT_INDEX}'")
        if cursor.fetchone() is None:
            cursor.execute(f"ALTER TABLE llm_log ADD INDEX {_CREATED_AT_INDEX} (created_at)")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[WARNING] Failed to ensure index on llm_log.created_at: {e}")


def get_total_tokens_last_hour(window_minutes=TPH_WINDOW_MINUTES):
    """Sum ``total_tokens`` over the trailing sliding window (default 60 min).

    Used by the hourly token cap: the caller compares this against the configured
    limit at API entry. Fail-open: returns 0 on any error (or when the system
    database/llm_log is unavailable) so a metrics outage never blocks requests.
    """
    if sys_engine is None:
        return 0
    since = datetime.now() - timedelta(minutes=window_minutes)
    try:
        with sys_engine.connect() as conn:
            total = conn.execute(
                select(func.coalesce(func.sum(llm_log.c.total_tokens), 0)).where(
                    llm_log.c.created_at >= since
                )
            ).scalar()
        return int(total or 0)
    except Exception as e:
        print(f"查询LLM token用量失败: {e}")
        return 0


def sanitize_messages(messages):
    """Return a copy of the chat messages with image payloads removed.

    Multimodal content is a list of parts; ``image_url`` parts carry the
    base64 data URL (or a URL) and are dropped, while the accompanying ``text``
    parts (which hold the image file names) are kept. Plain string content is
    returned unchanged.
    """
    sanitized = []
    for message in messages or []:
        if not isinstance(message, dict):
            sanitized.append(message)
            continue
        content = message.get("content")
        if isinstance(content, list):
            kept = [
                part for part in content
                if not (isinstance(part, dict) and part.get("type") == "image_url")
            ]
            sanitized.append({**message, "content": kept})
        else:
            sanitized.append(message)
    return sanitized


def messages_to_json(messages):
    try:
        return json.dumps(sanitize_messages(messages), ensure_ascii=False)
    except (TypeError, ValueError):
        return ""


def _usage_value(usage, name):
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage.get(name)
    return getattr(usage, name, None)


def _extract_reasoning_tokens(usage):
    details = _usage_value(usage, "completion_tokens_details")
    if details is None:
        return None
    if isinstance(details, dict):
        return details.get("reasoning_tokens")
    return getattr(details, "reasoning_tokens", None)


def record_llm_call(session_id=None, input_json="", output="", usage=None,
                    first_token_ms=None, duration_ms=None):
    """Record one LLM call. Best-effort: never raises into the LLM path."""
    if sys_engine is None or not config_data.get("enable_llm_log", True):
        return
    try:
        with sys_engine.connect() as conn:
            conn.execute(
                insert(llm_log).values(
                    session_id=session_id or None,
                    input=input_json or "",
                    output=output or "",
                    prompt_tokens=_usage_value(usage, "prompt_tokens"),
                    completion_tokens=_usage_value(usage, "completion_tokens"),
                    total_tokens=_usage_value(usage, "total_tokens"),
                    reasoning_tokens=_extract_reasoning_tokens(usage),
                    first_token_ms=first_token_ms,
                    duration_ms=duration_ms,
                    created_at=datetime.now(),
                )
            )
            conn.commit()
    except Exception as e:
        print(f"记录LLM调用日志失败: {e}")
