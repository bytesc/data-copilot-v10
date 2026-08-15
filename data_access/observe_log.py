from datetime import datetime
from sqlalchemy import (
    Table, Column, Integer, String, Text, DateTime, MetaData, insert, select, desc, func
)
import json

from data_access.sys_db_conn import sys_engine
from data_access.session_log import session_operation_log

metadata = MetaData()

observe_cycle_log = Table(
    "observe_cycle_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(255), nullable=False, comment="会话ID"),
    Column("cycle_index", Integer, nullable=False, comment="循环序号"),
    Column("phase", String(50), nullable=False, comment="阶段: think/execute/observe"),
    Column("sub_phase", String(100), comment="子阶段: filter_db/filter_func/plan/gen_code/exec_code/result"),
    Column("prompt", Text, comment="发送给LLM的prompt"),
    Column("response", Text, comment="LLM返回的响应"),
    Column("user_decision", String(50), comment="用户决策: approve/reject/edit/skip"),
    Column("exec_code", Text, comment="执行的代码"),
    Column("exec_result", Text, comment="执行结果"),
    Column("exec_error", Text, comment="执行错误"),
    Column("token_estimate", Integer, comment="token估算"),
    Column("created_at", DateTime, comment="记录时间"),
)

observe_session_log = Table(
    "observe_session_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(255), nullable=False, comment="会话ID"),
    Column("question", Text, comment="用户问题"),
    Column("status", String(50), comment="会话状态"),
    Column("total_cycles", Integer, comment="总循环次数"),
    Column("total_tokens", Integer, comment="总token数"),
    Column("conversation_history", Text, comment="完整对话上下文(JSON数组)"),
    Column("created_at", DateTime, comment="创建时间"),
    Column("updated_at", DateTime, comment="更新时间"),
)


def create_observe_log_tables():
    metadata.create_all(sys_engine)
    _ensure_column_exists(sys_engine, "observe_session_log", "conversation_history", "TEXT COMMENT 'conversation history' AFTER total_tokens")


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
        if not cursor.fetchone():
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
        conn.commit()
        conn.close()
    except Exception:
        pass


def log_observe_cycle(
    session_id,
    cycle_index,
    phase,
    sub_phase="",
    prompt="",
    response="",
    user_decision="",
    exec_code="",
    exec_result="",
    exec_error="",
    token_estimate=0,
):
    if not session_id:
        return
    try:
        with sys_engine.connect() as conn:
            conn.execute(
                insert(observe_cycle_log).values(
                    session_id=session_id,
                    cycle_index=cycle_index,
                    phase=phase,
                    sub_phase=sub_phase,
                    prompt=prompt[:10000] if prompt else "",
                    response=response[:10000] if response else "",
                    user_decision=user_decision,
                    exec_code=exec_code[:10000] if exec_code else "",
                    exec_result=exec_result[:10000] if exec_result else "",
                    exec_error=exec_error[:2000] if exec_error else "",
                    token_estimate=token_estimate,
                    created_at=datetime.now(),
                )
            )
            cycle_count = conn.execute(
                select(func.count()).select_from(observe_cycle_log).where(
                    observe_cycle_log.c.session_id == session_id
                )
            ).scalar()
            conn.execute(
                observe_session_log.update().where(
                    observe_session_log.c.session_id == session_id
                ).values(
                    total_cycles=cycle_count,
                    updated_at=datetime.now(),
                )
            )
            conn.commit()
    except Exception as e:
        print(f"记录观察日志失败: {e}")


def log_observe_session(session_id, question="", status="active", total_tokens=0):
    if not session_id:
        return
    try:
        with sys_engine.connect() as conn:
            existing = conn.execute(
                select(observe_session_log).where(
                    observe_session_log.c.session_id == session_id
                )
            ).fetchone()
            if existing:
                conn.execute(
                    observe_session_log.update().where(
                        observe_session_log.c.session_id == session_id
                    ).values(
                        status=status,
                        total_tokens=total_tokens,
                        updated_at=datetime.now(),
                    )
                )
            else:
                conn.execute(
                    insert(observe_session_log).values(
                        session_id=session_id,
                        question=question,
                        status=status,
                        total_cycles=0,
                        total_tokens=total_tokens,
                        created_at=datetime.now(),
                        updated_at=datetime.now(),
                    )
                )
            conn.commit()
    except Exception as e:
        print(f"记录会话日志失败: {e}")


def update_session_history(session_id, conversation_history):
    if not session_id:
        return
    try:
        import json
        history_json = json.dumps(conversation_history, ensure_ascii=False)
        with sys_engine.connect() as conn:
            existing = conn.execute(
                select(observe_session_log).where(
                    observe_session_log.c.session_id == session_id
                )
            ).fetchone()
            if existing:
                conn.execute(
                    observe_session_log.update().where(
                        observe_session_log.c.session_id == session_id
                    ).values(
                        conversation_history=history_json,
                        updated_at=datetime.now(),
                    )
                )
            conn.commit()
    except Exception as e:
        print(f"更新会话历史失败: {e}")


def get_session_history(session_id, limit=50):
    try:
        with sys_engine.connect() as conn:
            result = conn.execute(
                select(observe_cycle_log)
                .where(observe_cycle_log.c.session_id == session_id)
                .order_by(desc(observe_cycle_log.c.created_at))
                .limit(limit)
            ).fetchall()
            return [dict(row._mapping) for row in result]
    except Exception as e:
        print(f"查询会话历史失败: {e}")
        return []


def list_sessions(limit=50):
    try:
        with sys_engine.connect() as conn:
            result = conn.execute(
                select(observe_session_log)
                .order_by(desc(observe_session_log.c.updated_at))
                .limit(limit)
            ).fetchall()
            return [dict(row._mapping) for row in result]
    except Exception as e:
        print(f"查询会话列表失败: {e}")
        return []


def get_session_operations(session_id, limit=200):
    try:
        with sys_engine.connect() as conn:
            result = conn.execute(
                select(session_operation_log)
                .where(session_operation_log.c.session_id == session_id)
                .order_by(session_operation_log.c.created_at)
                .limit(limit)
            ).fetchall()
            return [dict(row._mapping) for row in result]
    except Exception as e:
        print(f"查询操作日志失败: {e}")
        return []


def get_session_cycles(session_id, limit=200):
    try:
        with sys_engine.connect() as conn:
            result = conn.execute(
                select(observe_cycle_log)
                .where(observe_cycle_log.c.session_id == session_id)
                .order_by(observe_cycle_log.c.created_at)
                .limit(limit)
            ).fetchall()
            return [dict(row._mapping) for row in result]
    except Exception as e:
        print(f"查询周期日志失败: {e}")
        return []


FRONTEND_ACTIONS = {"output_text", "ask_question", "ask_choice", "summary_and_pause", "attempt_completion"}


def _parse_action_decision(raw: str):
    try:
        raw = raw.strip()
        for prefix in ("```json", "```"):
            if raw.startswith(prefix):
                raw = raw[len(prefix):]
        for suffix in ("```",):
            if raw.endswith(suffix):
                raw = raw[:-len(suffix)]
        data = json.loads(raw.strip())
        action = data.get("action", "")
        if action in FRONTEND_ACTIONS:
            return action, data.get("text", "")
    except (json.JSONDecodeError, TypeError):
        pass
    return None, None


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
                history = json.loads(history_json)
            else:
                history = _rebuild_from_cycle_logs(conn, session_id, question)

        return {
            "session_id": session_id,
            "question": question,
            "status": session_info.get("status", ""),
            "total_cycles": session_info.get("total_cycles", 0),
            "total_tokens": session_info.get("total_tokens", 0),
            "created_at": str(session_info.get("created_at", "")),
            "updated_at": str(session_info.get("updated_at", "")),
            "conversation_history": history,
            "cycle_count": session_info.get("total_cycles", 0),
        }
    except Exception as e:
        print(f"重建会话历史失败: {e}")
        return None


def _rebuild_from_cycle_logs(conn, session_id, question):
    ops = conn.execute(
        select(session_operation_log)
        .where(session_operation_log.c.session_id == session_id)
        .order_by(session_operation_log.c.created_at)
    ).fetchall()

    cycles = conn.execute(
        select(observe_cycle_log)
        .where(observe_cycle_log.c.session_id == session_id)
        .order_by(observe_cycle_log.c.created_at)
    ).fetchall()

    all_entries = []
    for op in ops:
        opd = dict(op._mapping)
        all_entries.append((opd["created_at"], "op", opd))
    for cyc in cycles:
        cd = dict(cyc._mapping)
        all_entries.append((cd["created_at"], "cycle", cd))
    all_entries.sort(key=lambda x: x[0] if x[0] else datetime.min)

    history = []
    if question:
        history.append(f"Q: {question}")

    for ts, etype, entry in all_entries:
        if etype == "op":
            ep = entry.get("api_endpoint", "")
            if ep == "/api/generate-document/stream/":
                msg = entry.get("msg", "")
                history.append(f"[DOCUMENT] {msg}")
        elif etype == "cycle":
            phase = entry.get("phase", "")
            sub_phase = entry.get("sub_phase", "")
            response = entry.get("response", "") or ""
            exec_code = entry.get("exec_code", "") or ""
            exec_result = entry.get("exec_result", "") or ""
            exec_error = entry.get("exec_error", "") or ""
            user_decision = entry.get("user_decision", "") or ""
            if phase == "think" and sub_phase == "plan":
                if response:
                    history.append(f"[THINK] Plan:\n{response}")
            elif phase == "action" and sub_phase == "decide":
                if response:
                    history.append(f"[ACTION] Decision:\n{response}")
                    action_type, action_text = _parse_action_decision(response)
                    if action_type and action_text:
                        history.append(f"[ACT {action_type}] Output:\n{action_text}")
            elif phase == "observe" and sub_phase == "review":
                if response:
                    history.append(f"[OBSERVE] Review:\n{response}")
            elif phase == "act" and sub_phase == "explore_schema":
                if exec_result:
                    history.append(f"[ACT explore_schema] Results:\n{exec_result}")
            elif phase == "act" and sub_phase == "explore_functions":
                if exec_result:
                    history.append(f"[ACT explore_functions] Results:\n{exec_result}")
            elif phase == "act" and sub_phase == "generate_and_execute":
                if exec_code:
                    history.append(f"[ACT generate_and_execute] Code:\n{exec_code}")
                if exec_error:
                    history.append(f"[ACT generate_and_execute] Error:\n{exec_error}")
                elif exec_result:
                    history.append(f"[ACT generate_and_execute] Result:\n{exec_result}")
            elif phase == "user" and sub_phase == "input":
                if user_decision:
                    history.append(user_decision)

    return history