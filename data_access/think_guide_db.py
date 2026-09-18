from sqlalchemy import Table, Column, Text, MetaData, Integer
from sqlalchemy.dialects.mysql import LONGTEXT

from data_access.sys_db_conn import sys_engine

metadata = MetaData()

think_guide = Table(
    "think_guide", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True, comment="主键"),
    Column("key", Text, nullable=False, comment="思考指南键"),
    Column("value", LONGTEXT, comment="思考指南值"),
)


def create_think_guide_table():
    metadata.create_all(sys_engine)