import json
from sqlalchemy import select, insert
from data_access.sys_db_conn import sys_engine
from data_access.code_guide_db import code_guide
from agent.tools.copilot.utils.call_llm_test import call_llm
from agent.tools.tools_def import llm


def set_code_guide(text=""):
    if not text or not text.strip():
        return {"success": False, "error": "Empty input text"}

    existing_guide = _get_existing_guide()
    existing_text = "\n\n".join(f"### {k}\n{v}" for k, v in existing_guide.items()) if existing_guide else "*(None)*"

    prompt = f"""You are a chart code knowledge extraction expert. Extract structured knowledge from the user's input text.

## Existing Code Guide
{existing_text}

## Input Text
{text.strip()}

## Instructions
1. Analyze the input text and extract key knowledge points about graph/chart code generation.
2. Each key should be a short descriptive label (e.g. "color_palette", "chart_type_preference", "axis_format"), each value the knowledge content.
3. Output ONLY a valid JSON object (no markdown code block).
4. If the text provides no new useful knowledge, output an empty JSON object: {{}}.

Example:
```json
{{"color_palette": "Use blue and orange as primary colors", "chart_type_preference": "Prefer bar charts for categorical data and line charts for time series"}}
```
"""

    try:
        response = call_llm(prompt, llm)
        raw = response.content.strip()
    except Exception as e:
        print(f"[WARNING] Failed to call LLM for set_code_guide: {e}")
        return {"success": False, "error": f"LLM call failed: {e}"}

    knowledge = _parse_knowledge_json(raw)
    if not knowledge:
        return {"success": False, "error": "Failed to parse knowledge JSON", "raw": raw[:500]}

    try:
        saved = _save_guide(knowledge)
        return {"success": True, "saved": saved, "count": len(knowledge)}
    except Exception as e:
        print(f"[WARNING] Failed to save code_guide: {e}")
        return {"success": False, "error": f"DB save failed: {e}"}


def _get_existing_guide():
    try:
        with sys_engine.connect() as conn:
            result = conn.execute(select(code_guide))
            rows = result.fetchall()
            return {row.key: row.value for row in rows}
    except Exception as e:
        print(f"[WARNING] Failed to read existing code_guide: {e}")
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


def _save_guide(knowledge):
    with sys_engine.connect() as conn:
        trans = conn.begin()
        try:
            for key, value in knowledge.items():
                existing = conn.execute(
                    select(code_guide).where(code_guide.c.key == key)
                ).fetchone()
                if existing:
                    conn.execute(
                        code_guide.update().where(code_guide.c.key == key).values(value=str(value))
                    )
                else:
                    conn.execute(
                        insert(code_guide).values(key=key, value=str(value))
                    )
            trans.commit()
            return list(knowledge.keys())
        except Exception:
            trans.rollback()
            raise