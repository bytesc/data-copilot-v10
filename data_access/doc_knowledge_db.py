from sqlalchemy import Table, Column, Text, MetaData
from sqlalchemy.dialects.mysql import LONGTEXT

from data_access.sys_db_conn import sys_engine

metadata = MetaData()

doc_knowledge = Table(
    "doc_knowledge", metadata,
    Column("key", Text, nullable=False, comment="文档知识键"),
    Column("value", LONGTEXT, comment="文档知识值"),
)


def create_doc_knowledge_table():
    metadata.create_all(sys_engine)