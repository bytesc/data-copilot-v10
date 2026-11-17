import json
import threading
from datetime import datetime
from sqlalchemy import (
    Table, Column, Integer, String, DateTime, MetaData,
    insert, select, update, desc, or_
)
from sqlalchemy.dialects.mysql import LONGTEXT, TINYINT

from data_access.sys_db_conn import sys_engine
from data_access.session_log import session_operation_log


metadata = MetaData()

observe_session_log = Table(
    "observe_session_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(255), nullable=False, comment="会话ID"),
    Column("question", LONGTEXT, comment="用户问题"),
    Column("status", String(50), comment="会话状态"),
    Column("conversation_history", LONGTEXT, comment="完整对话上下文(JSON数组)"),
    Column("trimmed_context", LONGTEXT, comment="送给LLM的裁剪后上下文(JSON数组)"),
    Column("deleted", TINYINT, default=0, comment="是否已删除(1=已删除,0=未删除)"),
    Column("created_at", DateTime, comment="创建时间"),
    Column("updated_at", DateTime, comment="更新时间"),
)


# Serializes the check-then-create write of a session row so concurrent phase
# logs (think/action/act/observe) cannot both INSERT and create a duplicate
# session row. Logging is low volume, so a single process-wide lock is enough
# and avoids per-session bookkeeping.
_session_lock = threading.RLock()


def create_observe_log_tables():
    metadata.create_all(sys_engine)
    _ensure_column_exists(sys_engine, "observe_session_log", "question", "LONGTEXT COMMENT 'question'")
    _ensure_column_exists(sys_engine, "observe_session_log", "conversation_history", "LONGTEXT COMMENT 'conversation history' AFTER status")
    _ensure_column_exists(sys_engine, "observe_session_log", "trimmed_context", "LONGTEXT COMMENT 'trimmed context for LLM' AFTER conversation_history")
    _ensure_column_exists(sys_engine, "observe_session_log", "deleted", "TINYINT NOT NULL DEFAULT 0 COMMENT 'deleted flag' AFTER trimmed_context")
    # Drop the legacy character-length token estimate; real usage lives in llm_log.
    _drop_column_if_exists(sys_engine, "observe_session_log", "total_tokens")


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
    except Exception as e:
        print(
            f"[WARNING] Failed to ensure column '{column_name}' on table "
            f"'{table_name}': {e}"
        )


def _drop_column_if_exists(engine, table_name, column_name):
    import pymysql
    url = engine.url
    try:
        conn = pymysql.connect(
            host=url.host, port=url.port, user=url.username,
            password=url.password, database=url.database
        )
        cursor = conn.cursor()
        cursor.execute(f"SHOW COLUMNS FROM {table_name} LIKE '{column_name}'")
        if cursor.fetchone() is not None:
            cursor.execute(f"ALTER TABLE {table_name} DROP COLUMN {column_name}")
        conn.commit()
        conn.close()
    except Exception as e:
        print(
            f"[WARNING] Failed to drop column '{column_name}' on table "
            f"'{table_name}': {e}"
        )


def log_observe_session(session_id, question="", status="active"):
    if not session_id:
        return
    try:
        with sys_engine.connect() as conn:
            with _session_lock:
                existing = conn.execute(
                    select(observe_session_log.c.id).where(
                        observe_session_log.c.session_id == session_id
                    )
                ).fetchone()
                if existing is None:
                    conn.execute(
                        insert(observe_session_log).values(
                            session_id=session_id,
                            question=question,
                            status=status,
                            created_at=datetime.now(),
                            updated_at=datetime.now(),
                        )
                    )
                else:
                    conn.execute(
                        observe_session_log.update().where(
                            observe_session_log.c.session_id == session_id
                        ).values(
                            status=status,
                            updated_at=datetime.now(),
                        )
                    )
                conn.commit()
    except Exception as e:
        print(f"记录会话日志失败: {e}")


def save_session_context(session_id, conversation_history, trimmed_context):
    if not session_id:
        return
    try:
        history_json = json.dumps(conversation_history or [], ensure_ascii=False)
        context_json = json.dumps(trimmed_context or [], ensure_ascii=False)
        with sys_engine.connect() as conn:
            with _session_lock:
                existing = conn.execute(
                    select(observe_session_log.c.id).where(
                        observe_session_log.c.session_id == session_id
                    )
                ).fetchone()
                if existing is None:
                    conn.execute(
                        insert(observe_session_log).values(
                            session_id=session_id,
                            conversation_history=history_json,
                            trimmed_context=context_json,
                            created_at=datetime.now(),
                            updated_at=datetime.now(),
                        )
                    )
                else:
                    conn.execute(
                        observe_session_log.update().where(
                            observe_session_log.c.session_id == session_id
                        ).values(
                            conversation_history=history_json,
                            trimmed_context=context_json,
                            updated_at=datetime.now(),
                        )
                    )
                conn.commit()
    except Exception as e:
        print(f"保存会话上下文失败: {e}")


def _serialize_row(row_dict):
    return {
        k: v.isoformat() if isinstance(v, datetime) else v
        for k, v in row_dict.items()
    }


def list_sessions(limit=50, include_deleted=False):
    try:
        with sys_engine.connect() as conn:
            query = select(
                observe_session_log.c.id,
                observe_session_log.c.session_id,
                observe_session_log.c.question,
                observe_session_log.c.status,
                observe_session_log.c.deleted,
                observe_session_log.c.created_at,
                observe_session_log.c.updated_at,
            )
            if not include_deleted:
                query = query.where(
                    or_(
                        observe_session_log.c.deleted == 0,
                        observe_session_log.c.deleted.is_(None),
                    )
                )
            result = conn.execute(
                query.order_by(desc(observe_session_log.c.updated_at)).limit(limit)
            ).fetchall()
            return [_serialize_row(dict(row._mapping)) for row in result]
    except Exception as e:
        print(f"查询会话列表失败: {e}")
        return []


def set_session_deleted(session_id, deleted):
    """Soft-delete or restore a session. Returns False when it does not exist."""
    if not session_id:
        return False
    try:
        with sys_engine.connect() as conn:
            existing = conn.execute(
                select(observe_session_log.c.id).where(
                    observe_session_log.c.session_id == session_id
                )
            ).fetchone()
            if existing is None:
                return False
            conn.execute(
                update(observe_session_log)
                .where(observe_session_log.c.session_id == session_id)
                .values(deleted=1 if deleted else 0)
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"更新会话删除状态失败: {e}")
        return False


def delete_session(session_id):
    return set_session_deleted(session_id, True)


def restore_session(session_id):
    return set_session_deleted(session_id, False)


def get_session_operations(session_id, limit=200):
    try:
        with sys_engine.connect() as conn:
            result = conn.execute(
                select(session_operation_log)
                .where(session_operation_log.c.session_id == session_id)
                .order_by(session_operation_log.c.created_at)
                .limit(limit)
            ).fetchall()
            return [_serialize_row(dict(row._mapping)) for row in result]
    except Exception as e:
        print(f"查询操作日志失败: {e}")
        return []


def reconstruct_conversation_history(session_id):
    try:
        with sys_engine.connect() as conn:
            session_row = conn.execute(
                select(observe_session_log).where(
                    observe_session_log.c.session_id == session_id
                )
            ).fetchone()
            if not session_row:
                return None

            session_info = dict(session_row._mapping)
            question = session_info.get("question", "")
            history_json = session_info.get("conversation_history", "")

            if history_json:
                history = json.loads(history_json) or []
            else:
                history = []
            if not history:
                history = _rebuild_from_operations(conn, session_id, question)

        return {
            "session_id": session_id,
            "question": question,
            "status": session_info.get("status", ""),
            "created_at": str(session_info.get("created_at", "")),
            "updated_at": str(session_info.get("updated_at", "")),
            "conversation_history": history,
        }
    except Exception as e:
        print(f"重建会话历史失败: {e}")
        return None


def _rebuild_from_operations(conn, session_id, question):
    """Best-effort history rebuild from operation logs.

    Used only when ``observe_session_log.conversation_history`` is empty. The
    per-cycle log has been removed, so only document-generation operations can
    be recovered here; richer phase context is no longer available from the
    database and must come from the persisted conversation history instead.
    """
    ops = conn.execute(
        select(session_operation_log)
        .where(session_operation_log.c.session_id == session_id)
        .order_by(session_operation_log.c.created_at)
    ).fetchall()

    history = []
    if question:
        history.append({"role": "user", "type": "question", "content": question})

    for op in ops:
        opd = dict(op._mapping)
        if opd.get("api_endpoint") == "/api/generate-document/stream/":
            history.append({
                "role": "assistant",
                "type": "document",
                "content": opd.get("msg", ""),
            })

    return history
