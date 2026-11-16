import json
from datetime import datetime

from sqlalchemy import (
    Table, Column, Integer, String, DateTime, MetaData, insert
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
    Column("created_at", DateTime, comment="记录时间"),
)


def create_llm_log_table():
    if sys_engine is None:
        return
    metadata.create_all(sys_engine)


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
