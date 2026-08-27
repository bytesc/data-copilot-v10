from sqlalchemy import Table, Column, Text, MetaData, select
from sqlalchemy.dialects.mysql import LONGTEXT

from data_access.sys_db_conn import sys_engine

metadata = MetaData()

brief_info = Table(
    "brief_info", metadata,
    Column("attr", Text, nullable=False, comment="属性名称"),
    Column("value", LONGTEXT, comment="属性值"),
)


def create_brief_info_table():
    metadata.create_all(sys_engine)


def init_brief_info():
    _entries = [
        ("db_brief", ""),
        ("base_knowledge_brief", ""),
    ]
    try:
        with sys_engine.connect() as conn:
            for attr_name, md_content in _entries:
                existing = conn.execute(
                    select(brief_info).where(brief_info.c.attr == attr_name)
                ).fetchone()
                if existing is None:
                    conn.execute(
                        brief_info.insert().values(attr=attr_name, value=md_content)
                    )
                    print(f"[INFO] Inserted brief_info: {attr_name}")
                else:
                    conn.execute(
                        brief_info.update().where(brief_info.c.attr == attr_name).values(value=md_content)
                    )
                    print(f"[INFO] Updated brief_info: {attr_name}")
            conn.commit()
    except Exception as e:
        print(f"[WARNING] Failed to init brief_info: {e}")