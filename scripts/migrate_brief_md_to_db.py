import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, update
from data_access.sys_db_conn import sys_engine
from data_access.brief_info_db import brief_info

_KNOWLEDGE_DOCS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "agent", "tools", "base_knowledge", "knowledge_docs"
)

_FILE_MAP = {
    "db_brief": "db_brief.md",
    "base_knowledge_brief": "base_knowledge_brief.md",
    "mcp_brief": "mcp_brief.md",
    "function_brief": "function_brief.md",
}


def _read_md(attr_name):
    filename = _FILE_MAP.get(attr_name)
    if not filename:
        return ""
    filepath = os.path.join(_KNOWLEDGE_DOCS_DIR, filename)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        print(f"[WARNING] Failed to read {filepath}: {e}")
        return ""


def main():
    print("Starting migration: MD files -> brief_info table ...")
    with sys_engine.connect() as conn:
        for attr_name in _FILE_MAP:
            md_content = _read_md(attr_name)
            existing = conn.execute(
                select(brief_info).where(brief_info.c.attr == attr_name)
            ).fetchone()
            if existing is None:
                conn.execute(
                    brief_info.insert().values(attr=attr_name, value=md_content)
                )
                print(f"  [INSERTED] {attr_name} ({len(md_content)} chars)")
            else:
                conn.execute(
                    update(brief_info)
                    .where(brief_info.c.attr == attr_name)
                    .values(value=md_content)
                )
                print(f"  [UPDATED] {attr_name} ({len(md_content)} chars)")
        conn.commit()
    print("Migration complete.")


if __name__ == "__main__":
    main()