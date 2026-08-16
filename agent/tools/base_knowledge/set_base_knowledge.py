import json
from sqlalchemy import select, insert, delete
from data_access.sys_db_conn import sys_engine
from data_access.base_knowledge_db import base_knowledge
from agent.tools.copilot.utils.call_llm_test import call_llm
from agent.tools.tools_def import llm, engine
from agent.tools.search_db import get_db_structure_markdown


def set_base_knowledge(text=""):
    if not text or not text.strip():
        return {"success": False, "error": "Empty input text"}

    existing_knowledge = _get_existing_knowledge()
    existing_text = "\n\n".join(f"### {k}\n{v}" for k, v in existing_knowledge.items()) if existing_knowledge else "*(None)*"
    db_structure_text = get_db_structure_markdown(engine)

    prompt = f"""You are a knowledge extraction expert. Extract structured knowledge from the user's input text.

## Existing Knowledge
{existing_text}

## Database Structure
{db_structure_text}

## Input Text
{text.strip()}

## Instructions
1. Analyze the input text and extract key knowledge points.
2. If the text involves database queries, also include a `query_plan` key with a natural language query plan describing:
   - Which tables and fields to use
   - How to join, aggregate, filter, and sort
   - Do NOT write SQL code, only natural language description.
3. Output ONLY a valid JSON object (no markdown code block). Each key should be a short descriptive label, each value the knowledge content.
4. If the text provides no new useful knowledge, output an empty JSON object: {{}}.

Example:
```json
{{"user_analysis_needs": "The user wants monthly sales data by region", "query_plan": "Use the orders table and regions table, join on region_id, group by region and month, sum the amount field"}}
```
"""

    try:
        response = call_llm(prompt, llm)
        raw = response.content.strip()
    except Exception as e:
        print(f"[WARNING] Failed to call LLM for set_base_knowledge: {e}")
        return {"success": False, "error": f"LLM call failed: {e}"}

    knowledge = _parse_knowledge_json(raw)
    if not knowledge:
        return {"success": False, "error": "Failed to parse knowledge JSON", "raw": raw[:500]}

    try:
        saved = _save_knowledge(knowledge)
        return {"success": True, "saved": saved, "count": len(knowledge)}
    except Exception as e:
        print(f"[WARNING] Failed to save base_knowledge: {e}")
        return {"success": False, "error": f"DB save failed: {e}"}


def _get_existing_knowledge():
    try:
        with sys_engine.connect() as conn:
            result = conn.execute(select(base_knowledge))
            rows = result.fetchall()
            return {row.key: row.value for row in rows}
    except Exception as e:
        print(f"[WARNING] Failed to read existing knowledge: {e}")
        return {}


def _parse_knowledge_json(raw):
    raw = raw.strip()
    for prefix in ("```json", "```"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
    for suffix in ("```",):
        if raw.endswith(suffix):
            raw = raw[:-len(suffix)]
    raw = raw.strip()
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    return {}


def _save_knowledge(knowledge):
    with sys_engine.connect() as conn:
        trans = conn.begin()
        try:
            for key, value in knowledge.items():
                existing = conn.execute(
                    select(base_knowledge).where(base_knowledge.c.key == key)
                ).fetchone()
                if existing:
                    conn.execute(
                        base_knowledge.update().where(base_knowledge.c.key == key).values(value=str(value))
                    )
                else:
                    conn.execute(
                        insert(base_knowledge).values(key=key, value=str(value))
                    )
            trans.commit()
            return list(knowledge.keys())
        except Exception:
            trans.rollback()
            raise
