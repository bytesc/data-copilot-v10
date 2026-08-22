import os
from sqlalchemy import select
from data_access.sys_db_conn import sys_engine
from data_access.base_knowledge_db import base_knowledge
from data_access.db_query_guide_db import db_query_guide
from data_access.doc_knowledge_db import doc_knowledge
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
            all_knowledge = {row.key: row.value for row in rows}

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
    return "\n\n".join(f"### {k}\n{v}" for k, v in knowledge.items())


def get_db_query_guide_db(key=None, threshold=0.3):
    try:
        with sys_engine.connect() as conn:
            rows = conn.execute(select(db_query_guide)).fetchall()
            all_guide = {row.key: row.value for row in rows}

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
            all_doc = {row.key: row.value for row in rows}

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


def get_base_knowledge_db_llm(context="", key=None):
    knowledge = get_base_knowledge_db(key)
    if not knowledge:
        yield ""
        return

    knowledge_text = base_knowledge_to_str(knowledge)
    db_structure_text = get_db_structure_markdown(engine)

    prompt = f"""You are a data analysis expert. Based on the following database knowledge and user context, generate a natural language query plan.

{knowledge_text}

{db_structure_text}

## User Context
{context}

## Instructions
Analyze the user's question against the database schema. Output a natural language query plan describing:
1. Which tables to use
2. Which fields/columns to select
3. How to join tables (if multiple tables are needed)
4. Any aggregation, grouping, filtering, or sorting needed
5. The reasoning behind the plan

Do NOT write any SQL code. Use plain natural language only."""

    try:
        for chunk in call_llm_stream(prompt, llm):
            yield chunk
    except Exception as e:
        print(f"[WARNING] Failed to get base_knowledge plan from LLM: {e}")
        yield ""


def get_db_query_guide_db_llm(context="", key=None):
    guide = get_db_query_guide_db(key)
    if not guide:
        yield ""
        return

    guide_text = base_knowledge_to_str(guide)

    prompt = f"""You are a SQL query expert. Based on the following query guide and user context, generate a natural language query plan.

{guide_text}

## User Context
{context}

## Instructions
Analyze the user's question against the query guide. Output a natural language query plan describing:
1. Which tables to use
2. Which fields/columns to select
3. How to join tables (if multiple tables are needed)
4. Any aggregation, grouping, filtering, or sorting needed
5. The reasoning behind the plan

Do NOT write any SQL code. Use plain natural language only."""

    try:
        for chunk in call_llm_stream(prompt, llm):
            yield chunk
    except Exception as e:
        print(f"[WARNING] Failed to get db_query_guide plan from LLM: {e}")
        yield ""


def get_doc_knowledge_db_llm(context="", key=None):
    doc = get_doc_knowledge_db(key)
    if not doc:
        yield ""
        return

    doc_text = base_knowledge_to_str(doc)

    prompt = f"""You are a documentation expert. Based on the following document knowledge and user context, generate a natural language query plan.

{doc_text}

## User Context
{context}

## Instructions
Analyze the user's question against the document knowledge. Output a natural language query plan describing:
1. Which tables to use
2. Which fields/columns to select
3. How to join tables (if multiple tables are needed)
4. Any aggregation, grouping, filtering, or sorting needed
5. The reasoning behind the plan

Do NOT write any SQL code. Use plain natural language only."""

    try:
        for chunk in call_llm_stream(prompt, llm):
            yield chunk
    except Exception as e:
        print(f"[WARNING] Failed to get doc_knowledge plan from LLM: {e}")
        yield ""


DB_BRIEF = "\nDataBase Brief:\n"+_read_doc("db_brief.md")


DB_QUERY_GUIDE = ""

# DB_QUERY_GUIDE = "\nSQL Query guide:\n"+_read_doc("db_quiery_guide.md")\
# +"\n" + base_knowledge_to_str(get_db_query_guide_db())


BASE = "\nbase knowledge for reference:\n"+_read_doc("base_knowledge.md")\
       +"\n" + base_knowledge_to_str(get_base_knowledge_db())

DOC = "\ndoc reference(just for reference):\n"+_read_doc("doc_knowledge.md")\
+"\n" + base_knowledge_to_str(get_doc_knowledge_db())


TARGET = "\nTarget:\n"+_read_doc("target_knowledge.md")
