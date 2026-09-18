import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, update
from data_access.sys_db_conn import sys_engine
from data_access.db_query_guide_db import db_query_guide

_KNOWLEDGE_DOCS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "agent", "tools", "base_knowledge", "knowledge_docs"
)


def _read_md():
    filepath = os.path.join(_KNOWLEDGE_DOCS_DIR, "db_query_guide.md")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        print(f"[WARNING] Failed to read {filepath}: {e}")
        return ""


def main():
    content = _read_md()
    if not content:
        print("db_query_guide.md is empty, nothing to migrate.")
        return

    key = "SQL Query Guide"
    with sys_engine.connect() as conn:
        existing = conn.execute(
            select(db_query_guide).where(db_query_guide.c.key == key)
        ).fetchone()
        if existing is None:
            conn.execute(
                db_query_guide.insert().values(key=key, value=content)
            )
            print(f"  [INSERTED] {key} ({len(content)} chars)")
        else:
            conn.execute(
                update(db_query_guide)
                .where(db_query_guide.c.key == key)
                .values(value=content)
            )
            print(f"  [UPDATED] {key} ({len(content)} chars)")
        conn.commit()
    print("Migration complete.")


if __name__ == "__main__":
    main()