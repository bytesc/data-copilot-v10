from sqlalchemy import Table, Column, Text, MetaData
from sqlalchemy.dialects.mysql import LONGTEXT

from data_access.sys_db_conn import sys_engine

metadata = MetaData()

doc_guide = Table(
    "doc_guide", metadata,
    Column("key", Text, nullable=False, comment="文档指南键"),
    Column("value", LONGTEXT, comment="文档指南值"),
)


def create_doc_guide_table():
    metadata.create_all(sys_engine)