from datetime import datetime
from sqlalchemy import (
    Table, Column, Integer, String, Text, DateTime, MetaData, insert, select, desc
)

from data_access.sys_db_conn import sys_engine

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
    Column("created_at", DateTime, comment="创建时间"),
    Column("updated_at", DateTime, comment="更新时间"),
)


def create_observe_log_tables():
    metadata.create_all(sys_engine)


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
            conn.commit()
    except Exception as e:
        print(f"记录观察日志失败: {e}")


def log_observe_session(session_id, question="", status="active", total_cycles=0, total_tokens=0):
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
                        total_cycles=total_cycles,
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
                        total_cycles=total_cycles,
                        total_tokens=total_tokens,
                        created_at=datetime.now(),
                        updated_at=datetime.now(),
                    )
                )
            conn.commit()
    except Exception as e:
        print(f"记录会话日志失败: {e}")


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