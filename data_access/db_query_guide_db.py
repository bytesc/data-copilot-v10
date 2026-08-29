from sqlalchemy import Table, Column, Integer, Text, MetaData
from sqlalchemy.dialects.mysql import LONGTEXT

from data_access.sys_db_conn import sys_engine

metadata = MetaData()

db_query_guide = Table(
    "db_query_guide", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("key", Text, nullable=False, comment="查询指南键"),
    Column("value", LONGTEXT, comment="查询指南值"),
)


def create_db_query_guide_table():
    metadata.create_all(sys_engine)