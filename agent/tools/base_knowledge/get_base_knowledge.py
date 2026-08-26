import json
import os
import re
from sqlalchemy import select
from data_access.sys_db_conn import sys_engine
from data_access.base_knowledge_db import base_knowledge
from data_access.db_query_guide_db import db_query_guide
from data_access.doc_knowledge_db import doc_knowledge
from data_access.graph_code_guide_db import graph_code_guide
from agent.tools.copilot.utils.call_llm_test import call_llm_stream
from agent.tools.tools_def import llm, engine
from agent.tools.search_db import get_db_structure_markdown

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


def base_knowledge_to_str(knowledge):
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


def get_doc_knowledge_db(key=None, threshold=0.3):
    try:
        with sys_engine.connect() as conn:
            rows = conn.execute(select(doc_knowledge)).fetchall()
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
        print(f"[WARNING] Failed to read doc_knowledge from db: {e}")
        return {}


def _parse_llm_response_with_ids(raw):
    try:
        match = re.search(r'```json\s*(.*?)\s*```', raw, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
        else:
            data = json.loads(raw)
        description = data.get("description", "")
        useful_ids = data.get("useful_ids", [])
        return description, useful_ids
    except Exception:
        return raw, []


def _llm_search_with_ids(prompt, knowledge):
    yield {"type": "status", "content": "正在分析知识库..."}
    full_content = ""
    for chunk in call_llm_stream(prompt, llm):
        full_content += chunk
        yield {"type": "chunk", "content": chunk}

    description, useful_ids = _parse_llm_response_with_ids(full_content)
    yield {"type": "done", "description": description, "useful_ids": useful_ids}


def _build_knowledge_context(knowledge_text, extra_text, role_label, context, instructions):
    return f"""You are a {role_label}. Based on the following knowledge and user context, generate a response.

## Knowledge
{knowledge_text}

{extra_text}

## User Context
{context}

## Instructions
{instructions}

## Output Format
Output ONLY a valid JSON object inside a ```json code block:
```json
{{
    "description": "your natural language description or analysis here",
    "useful_ids": [1, 3, 5]
}}
```

The `useful_ids` should be a list of knowledge entry IDs that are relevant to the user's context. If no entries are relevant, use an empty list `[]`."""


def get_base_knowledge_db_llm(context="", key=None):
    knowledge = get_base_knowledge_db(key)
    if not knowledge:
        yield {"type": "done", "description": "", "useful_ids": []}
        return

    knowledge_text = base_knowledge_to_str(knowledge)
    db_structure_text = get_db_structure_markdown(engine)

    prompt = _build_knowledge_context(
        knowledge_text, db_structure_text,
        "data analysis expert",
        context,
        "Analyze the user's question against the database schema. Output a natural language query plan describing:\n"
        "1. Which tables to use\n"
        "2. Which fields/columns to select\n"
        "3. How to join tables (if multiple tables are needed)\n"
        "4. Any aggregation, grouping, filtering, or sorting needed\n"
        "5. The reasoning behind the plan\n"
        "Do NOT write any SQL code."
    )

    yield from _llm_search_with_ids(prompt, knowledge)


def get_db_query_guide_db_llm(context="", key=None):
    guide = get_db_query_guide_db(key)
    if not guide:
        yield {"type": "done", "description": "", "useful_ids": []}
        return

    guide_text = base_knowledge_to_str(guide)

    prompt = _build_knowledge_context(
        guide_text, "",
        "SQL query expert",
        context,
        "Analyze the user's question against the query guide. Output a natural language query plan describing:\n"
        "1. Which tables to use\n"
        "2. Which fields/columns to select\n"
        "3. How to join tables (if multiple tables are needed)\n"
        "4. Any aggregation, grouping, filtering, or sorting needed\n"
        "5. The reasoning behind the plan\n"
        "Do NOT write any SQL code."
    )

    yield from _llm_search_with_ids(prompt, guide)


def get_doc_knowledge_db_llm(context="", key=None):
    doc = get_doc_knowledge_db(key)
    if not doc:
        yield {"type": "done", "description": "", "useful_ids": []}
        return

    doc_text = base_knowledge_to_str(doc)

    prompt = _build_knowledge_context(
        doc_text, "",
        "documentation expert",
        context,
        "Analyze the user's question against the document knowledge. Output a natural language query plan describing:\n"
        "1. Which tables to use\n"
        "2. Which fields/columns to select\n"
        "3. How to join tables (if multiple tables are needed)\n"
        "4. Any aggregation, grouping, filtering, or sorting needed\n"
        "5. The reasoning behind the plan\n"
        "Do NOT write any SQL code."
    )

    yield from _llm_search_with_ids(prompt, doc)


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


def get_graph_code_guide_db_llm(context="", key=None):
    guide = get_graph_code_guide_db(key)
    if not guide:
        yield {"type": "done", "description": "", "useful_ids": []}
        return

    guide_text = base_knowledge_to_str(guide)

    prompt = _build_knowledge_context(
        guide_text, "",
        "chart code expert",
        context,
        "Analyze the user's question against the graph code guide. Output a natural language query plan describing:\n"
        "1. Which chart type to use\n"
        "2. Which data fields to use for axes\n"
        "3. How to aggregate or group data\n"
        "4. Any custom styling or formatting\n"
        "5. The reasoning behind the plan\n"
        "Do NOT write any Python code."
    )

    yield from _llm_search_with_ids(prompt, guide)


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
_DOC_MD = _read_doc("doc_knowledge.md")
_TARGET_MD = _read_doc("target_knowledge.md")
_DB_QUERY_GUIDE_MD = _read_doc("db_query_guide.md")


DB_BRIEF = _DynamicStr(lambda: "\nDataBase Brief:\n" + _DB_BRIEF_MD)


DB_QUERY_GUIDE = _DynamicStr(lambda: "")

# DB_QUERY_GUIDE = _DynamicStr(lambda: "\nSQL Query guide:\n" + _DB_QUERY_GUIDE_MD\
# + "\n" + base_knowledge_to_str(get_db_query_guide_db()))


BASE = _DynamicStr(lambda: "\nbase knowledge for reference:\n" + _BASE_MD\
       + "\n" + base_knowledge_to_str(get_base_knowledge_db()))

DOC = _DynamicStr(lambda: "\ndoc reference(just for reference):\n" + _DOC_MD\
+ "\n" + base_knowledge_to_str(get_doc_knowledge_db()))


TARGET = _DynamicStr(lambda: "\nTarget:\n" + _TARGET_MD)
