from sqlalchemy import Table, Column, Text, MetaData, Integer
from sqlalchemy.dialects.mysql import LONGTEXT

from data_access.sys_db_conn import sys_engine

metadata = MetaData()

think_knowledge = Table(
    "think_knowledge", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True, comment="主键"),
    Column("key", Text, nullable=False, comment="思考知识键"),
    Column("value", LONGTEXT, comment="思考知识值"),
)


def create_think_knowledge_table():
    metadata.create_all(sys_engine)