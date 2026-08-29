import json
from typing import List


FRONTEND_ACTIONS = {"output_text", "ask_question", "ask_choice", "summary_and_pause", "attempt_completion"}


def history_to_text(history: List[dict]) -> str:
    lines = []
    for entry in history:
        role = entry.get("role", "")
        entry_type = entry.get("type", "")
        if role == "user":
            utype = entry.get("type", "question")
            content = entry.get("content", "")
            if utype == "question":
                lines.append(f"Q: {content}")
            elif utype == "choice":
                lines.append(f"User chose: {content}")
            elif utype == "response":
                lines.append(f"User response: {content}")
            elif utype == "input":
                lines.append(f"User: {content}")
        elif entry_type == "think":
            content = entry.get("content", "")
            lines.append(f"[THINK] content:\n{json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else content}")
        elif entry_type == "action_decision":
            content = entry.get("content", "")
            lines.append(f"[ACTION] content:\n{json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else content}")
        elif entry_type == "act":
            action = entry.get("action", "")
            if action == "explore_schema":
                if entry.get("selected_fields") is not None:
                    lines.append(f"[ACT explore_schema] selected_fields: {json.dumps(entry['selected_fields'], ensure_ascii=False)}")
                if entry.get("explore_plan"):
                    lines.append(f"[ACT explore_schema] explore_plan:\n{entry['explore_plan']}")
                if entry.get("selected_guides"):
                    lines.append(f"[ACT explore_schema] selected_guides: {json.dumps(entry['selected_guides'])}")
                if entry.get("query_guide_content"):
                    lines.append(f"[ACT explore_schema] query_guide_content:\n{entry['query_guide_content']}")
                if entry.get("schema_detail"):
                    lines.append(f"[ACT explore_schema] schema_detail:\n{entry['schema_detail']}")
            elif action == "explore_functions":
                if entry.get("selected_functions") is not None:
                    lines.append(f"[ACT explore_functions] selected_functions: {json.dumps(entry['selected_functions'], ensure_ascii=False)}")
                if entry.get("func_docs"):
                    lines.append(f"[ACT explore_functions] func_docs:\n{entry['func_docs']}")
            elif action == "generate_and_execute":
                if entry.get("code"):
                    lines.append(f"[ACT generate_and_execute] code:\n{entry['code']}")
                if entry.get("error"):
                    lines.append(f"[ACT generate_and_execute] error:\n{entry['error']}")
                elif entry.get("result"):
                    lines.append(f"[ACT generate_and_execute] result:\n{entry['result']}")
            elif action == "generate_document":
                if entry.get("file_name"):
                    lines.append(f"[ACT generate_document] file_name: {entry['file_name']}.md / {entry['file_name']}.docx")
                if entry.get("full_text"):
                    lines.append(f"[ACT generate_document] full_text:\n{entry['full_text']}")
            elif action == "solved":
                if entry.get("solved_ans"):
                    lines.append(f"[ACT] solved_ans:\n{entry['solved_ans']}")
            elif action in FRONTEND_ACTIONS:
                if entry.get("text"):
                    lines.append(f"[ACT {action}] text:\n{entry['text']}")
            elif action == "fetch_webpage":
                if entry.get("page_content"):
                    lines.append(f"[ACT {action}] page_content:\n{entry['page_content']}")
            else:
                if entry.get("search_result"):
                    lines.append(f"[ACT {action}] search_result:\n{entry['search_result']}")
        elif entry_type == "observe":
            action = entry.get("action", "")
            content = entry.get("content", "")
            lines.append(f"[OBSERVE] content:\n{json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else content}")
    return "\n".join(lines)