from sqlalchemy import Table, Column, Text, Integer, MetaData
from sqlalchemy.dialects.mysql import LONGTEXT

from data_access.sys_db_conn import sys_engine

metadata = MetaData()

base_knowledge = Table(
    "base_knowledge", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True, comment="主键"),
    Column("key", Text, nullable=False, comment="基础知识键"),
    Column("value", LONGTEXT, comment="基础知识值"),
)


def create_base_knowledge_table():
    metadata.create_all(sys_engine)