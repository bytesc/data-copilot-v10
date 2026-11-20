import json
import os
import re
from sqlalchemy import select
from data_access.sys_db_conn import sys_engine
from data_access.base_knowledge_db import base_knowledge
from data_access.db_query_guide_db import db_query_guide
from data_access.doc_guide_db import doc_guide
from data_access.code_guide_db import code_guide
from data_access.graph_code_guide_db import graph_code_guide
from data_access.think_guide_db import think_guide
from data_access.brief_info_db import brief_info
from utils.get_config import config_data

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





def get_base_knowledge_db(key=None, threshold=0.3):
    try:
        with sys_engine.connect() as conn:
            rows = conn.execute(select(base_knowledge)).fetchall()
            all_knowledge = {row.key: {"id": row.id, "value": row.value} for row in rows}

        if not key:
            return all_knowledge

        from difflib import SequenceMatcher
        result = {}
        for db_key, db_value in all_knowledge.items():
            for search_key in key:
                if SequenceMatcher(None, search_key, db_key).ratio() >= threshold:
                    result[db_key] = db_value
                    break
        return result
    except Exception as e:
        print(f"[WARNING] Failed to read base_knowledge from db: {e}")
        return {}


def base_knowledge_to_str(knowledge, with_ids=False):
    if with_ids:
        return "\n\n".join(f"### [id={v['id']}] {k}\n{v['value']}" for k, v in knowledge.items())
    return "\n\n".join(f"### {k}\n{v['value']}" for k, v in knowledge.items())


def get_db_query_guide_db(key=None, threshold=0.3):
    try:
        with sys_engine.connect() as conn:
            rows = conn.execute(select(db_query_guide)).fetchall()
            all_guide = {row.key: {"id": row.id, "value": row.value} for row in rows}

        if not key:
            return all_guide

        from difflib import SequenceMatcher
        result = {}
        for db_key, db_value in all_guide.items():
            for search_key in key:
                if SequenceMatcher(None, search_key, db_key).ratio() >= threshold:
                    result[db_key] = db_value
                    break
        return result
    except Exception as e:
        print(f"[WARNING] Failed to read db_query_guide from db: {e}")
        return {}


def get_doc_guide_db(key=None, threshold=0.3):
    try:
        with sys_engine.connect() as conn:
            rows = conn.execute(select(doc_guide)).fetchall()
            all_doc = {row.key: {"id": row.id, "value": row.value} for row in rows}

        if not key:
            return all_doc

        from difflib import SequenceMatcher
        result = {}
        for db_key, db_value in all_doc.items():
            for search_key in key:
                if SequenceMatcher(None, search_key, db_key).ratio() >= threshold:
                    result[db_key] = db_value
                    break
        return result
    except Exception as e:
        print(f"[WARNING] Failed to read doc_guide from db: {e}")
        return {}


def get_code_guide_db(key=None, threshold=0.3):
    try:
        with sys_engine.connect() as conn:
            rows = conn.execute(select(code_guide)).fetchall()
            all_guide = {row.key: {"id": row.id, "value": row.value} for row in rows}

        if not key:
            return all_guide

        from difflib import SequenceMatcher
        result = {}
        for db_key, db_value in all_guide.items():
            for search_key in key:
                if SequenceMatcher(None, search_key, db_key).ratio() >= threshold:
                    result[db_key] = db_value
                    break
        return result
    except Exception as e:
        print(f"[WARNING] Failed to read code_guide from db: {e}")
        return {}


def get_graph_code_guide_db(key=None, threshold=0.3):
    try:
        with sys_engine.connect() as conn:
            rows = conn.execute(select(graph_code_guide)).fetchall()
            all_guide = {row.key: {"id": row.id, "value": row.value} for row in rows}

        if not key:
            return all_guide

        from difflib import SequenceMatcher
        result = {}
        for db_key, db_value in all_guide.items():
            for search_key in key:
                if SequenceMatcher(None, search_key, db_key).ratio() >= threshold:
                    result[db_key] = db_value
                    break
        return result
    except Exception as e:
        print(f"[WARNING] Failed to read graph_code_guide from db: {e}")
        return {}


def get_think_guide_db(key=None, threshold=0.3):
    try:
        with sys_engine.connect() as conn:
            rows = conn.execute(select(think_guide)).fetchall()
            all_knowledge = {row.key: {"id": row.id, "value": row.value} for row in rows}

        if not key:
            return all_knowledge

        from difflib import SequenceMatcher
        result = {}
        for db_key, db_value in all_knowledge.items():
            for search_key in key:
                if SequenceMatcher(None, search_key, db_key).ratio() >= threshold:
                    result[db_key] = db_value
                    break
        return result
    except Exception as e:
        print(f"[WARNING] Failed to read think_guide from db: {e}")
        return {}


class _DynamicStr:
    def __init__(self, func):
        self.func = func
    def __str__(self):
        return self.func()
    def __add__(self, other):
        return str(self) + other
    def __radd__(self, other):
        return other + str(self)
    def strip(self):
        return str(self).strip()
    def __format__(self, format_spec):
        return format(str(self), format_spec)
    def __repr__(self):
        return repr(str(self))


_DB_BRIEF_MD = _read_doc("db_brief.md")
_BASE_MD = _read_doc("base_knowledge.md")
_DOC_MD = _read_doc("doc_guide.md")
_TARGET_MD = _read_doc("target_knowledge.md")
_DB_QUERY_GUIDE_MD = _read_doc("db_query_guide.md")
_THINK_KNOWLEDGE_MD = _read_doc("think_guide.md")
_MCP_BRIEF_MD = _read_doc("mcp_brief.md")
_BASE_KNOWLEDGE_BRIEF_MD = _read_doc("base_knowledge_brief.md")
_CUSTOM_FUNC_BRIEF_MD = _read_doc("custom_func_brief.md")


def _get_brief_value(attr, md_fallback):
    try:
        with sys_engine.connect() as conn:
            rows = conn.execute(select(brief_info)).fetchall()
            row_map = {row.attr: row.value for row in rows}
        db_value = row_map.get(attr, "")
        if db_value:
            md_fallback += "\n\n" + db_value
    except Exception as e:
        print(f"[WARNING] Failed to read brief_info for {attr}: {e}")
    return md_fallback


def _get_db_brief():
    v = _get_brief_value("db_brief", _DB_BRIEF_MD)
    return ("\nDataBase Brief:\n" + v) if v.strip() else ""


DB_BRIEF = _DynamicStr(_get_db_brief)


def _get_mcp_brief():
    v = _get_brief_value("mcp_brief", _MCP_BRIEF_MD)
    return ("\nMCP Brief:\n" + v) if v.strip() else ""


MCP_BRIEF = _DynamicStr(_get_mcp_brief)
BASE_KNOWLEDGE_BRIEF = _DynamicStr(lambda: _get_brief_value("base_knowledge_brief", _BASE_KNOWLEDGE_BRIEF_MD))
CUSTOM_FUNC_BRIEF = _DynamicStr(lambda: _get_brief_value("custom_func_brief", _CUSTOM_FUNC_BRIEF_MD))


def _format_db_query_guide():
    md = _DB_QUERY_GUIDE_MD
    guide_db = get_db_query_guide_db()
    if guide_db:
        if md.strip():
            md += "\n\n"
        md += "\n\n".join(
            f"### [id={v['id']}] {k}\n{v['value']}" for k, v in guide_db.items()
        )
    return ("\nSQL Query guide:\n" + md) if md.strip() else ""

DB_QUERY_GUIDE = _DynamicStr(_format_db_query_guide)


BASE = _DynamicStr(lambda: "\nbase knowledge for reference:\n" + _BASE_MD\
       + "\n" + base_knowledge_to_str(get_base_knowledge_db()))

# MD-only portion of BASE (`base_knowledge.md`). Code generation injects this
# instead of BASE: the selected base knowledge is injected via the KNOWLEDGE
# blackboard region, so the full `base_knowledge` table dump would duplicate it.
BASE_MD = _DynamicStr(lambda: ("\nbase knowledge for reference:\n" + _BASE_MD) if _BASE_MD.strip() else "")

DOC = _DynamicStr(lambda: ("\ndoc reference(just for reference):\n" + _DOC_MD\
+ "\n" + base_knowledge_to_str(get_doc_guide_db())) if (_DOC_MD.strip() or get_doc_guide_db()) else "")


TARGET = _DynamicStr(lambda: ("\nTarget:\n" + _TARGET_MD) if _TARGET_MD else "")

THINK_KNOWLEDGE = _DynamicStr(lambda: ("\nthink knowledge for reference:\n" + _THINK_KNOWLEDGE_MD\
       + "\n" + base_knowledge_to_str(get_think_guide_db())) if (_THINK_KNOWLEDGE_MD.strip() or get_think_guide_db()) else "")


def _get_brief_info(enabled_knowledge=True, enabled_mcp=True):
    parts = []

    db = str(DB_BRIEF)
    if db.strip():
        parts.append(f"{db}\n\nUse `explore_schema` to explore table schemas and sample data.")

    if enabled_knowledge:
        bk = str(BASE_KNOWLEDGE_BRIEF)
        if bk.strip():
            parts.append(f"### Domain Knowledge Brief\n{bk}\n\nUse `explore_base_knowledge` to explore full business domain knowledge.")

    if enabled_mcp:
        mcp = str(MCP_BRIEF)
        if mcp.strip():
            parts.append(f"### MCP Brief\n{mcp}\n\nUse `explore_mcp` to explore available MCP tools.")

    func_hardcoded = """
Database:
- Execute SQL queries, load tables, get database schema
Visualization:
- Generate charts (line, bar, scatter, pie, etc.) and save images
"""
    parts.append(f"### Function Brief\n{func_hardcoded}\n\nUse `explore_functions` to explore available function details.")

    custom_func = str(CUSTOM_FUNC_BRIEF)
    if custom_func.strip():
        parts.append(f"### Custom Function Brief\n{custom_func}\n\nUse `explore_functions` to explore available function details.")

    return "\n\n".join(parts)


BRIEF_INFO = _DynamicStr(lambda: _get_brief_info(
    config_data.get('enable_base_knowledge', True),
    config_data.get('enable_mcp', True),
))



