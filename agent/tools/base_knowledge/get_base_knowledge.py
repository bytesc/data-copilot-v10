import os
from sqlalchemy import select
from data_access.sys_db_conn import sys_engine
from data_access.base_knowledge_db import base_knowledge

_KNOWLEDGE_DIR = os.path.dirname(os.path.abspath(__file__))
_DOCS_DIR = os.path.join(_KNOWLEDGE_DIR, "knowledge_docs")


def _read_doc(filename):
    try:
        filepath = os.path.join(_DOCS_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            if content.strip() != "":
                return f"```markdown\n{content}\n```"
            else:
                return ""
    except Exception as e:
        print(f"[WARNING] Failed to read {filename}: {e}")
        return ""


DB_BRIEF = _read_doc("db_brief.md")

DB_QUERY_GUIDE = _read_doc("db_quiery_guide.md")



BASE = _read_doc("base_knowledge.md")


def get_base_knowledge(key=""):
    knowledge = BASE
    return knowledge


def get_base_knowledge_db(key=""):
    try:
        with sys_engine.connect() as conn:
            result = conn.execute(select(base_knowledge))
            rows = result.fetchall()
            return {row.key: row.value for row in rows}
    except Exception as e:
        print(f"[WARNING] Failed to read base_knowledge from db: {e}")
        return {}
