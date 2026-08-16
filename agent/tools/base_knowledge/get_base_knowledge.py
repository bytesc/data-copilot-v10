import os
from sqlalchemy import select
from data_access.sys_db_conn import sys_engine
from data_access.base_knowledge_db import base_knowledge
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


def get_base_knowledge_db_llm(context=""):
    knowledge = get_base_knowledge_db()
    if not knowledge:
        yield ""
        return

    knowledge_text = "\n\n".join(f"### {k}\n{v}" for k, v in knowledge.items())
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






