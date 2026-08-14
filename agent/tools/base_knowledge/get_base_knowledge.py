import os

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


def get_base_knowledge(key=""):
    knowledge = ""
    return knowledge
