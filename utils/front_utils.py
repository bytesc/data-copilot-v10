import json
from typing import List


FRONTEND_ACTIONS = {"ask_question", "ask_choice", "summary_and_pause", "attempt_completion"}


def history_to_text(history: List[dict]) -> str:
    lines = []
    for entry in history:
        role = entry.get("role", "")
        entry_type = entry.get("type", "")
        if entry_type == "blackboard":
            continue
        if role == "user":
            utype = entry.get("type", "question")
            content = entry.get("content", "")
            suffix = ""
            uploaded = entry.get("uploaded")
            if isinstance(uploaded, list) and uploaded:
                names = []
                for item in uploaded:
                    if isinstance(item, str):
                        if item:
                            names.append(item)
                    elif isinstance(item, dict):
                        label = item.get("path") or item.get("filename") or item.get("name")
                        if label:
                            names.append(str(label))
                if names:
                    suffix = "\nUploaded images: " + ", ".join(names)
            if utype == "question":
                lines.append(f"Q: {content}{suffix}")
            elif utype == "choice":
                lines.append(f"User chose: {content}{suffix}")
            elif utype == "response":
                lines.append(f"User response: {content}{suffix}")
            elif utype == "input":
                lines.append(f"User: {content}{suffix}")
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
            elif action == "explore_base_knowledge":
                if entry.get("selected_knowledge_ids") is not None:
                    lines.append(f"[ACT explore_base_knowledge] selected_knowledge_ids: {json.dumps(entry['selected_knowledge_ids'], ensure_ascii=False)}")
                if entry.get("summary"):
                    lines.append(f"[ACT explore_base_knowledge] summary:\n{entry['summary']}")
            elif action == "explore_functions":
                if entry.get("selected_functions") is not None:
                    lines.append(f"[ACT explore_functions] selected_functions: {json.dumps(entry['selected_functions'], ensure_ascii=False)}")
                if entry.get("explore_plan"):
                    lines.append(f"[ACT explore_functions] explore_plan:\n{entry['explore_plan']}")
                if entry.get("error"):
                    lines.append(f"[ACT explore_functions] error:\n{entry['error']}")
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
            elif action == "web_search":
                if entry.get("search_result"):
                    lines.append(f"[ACT web_search] search_result:\n{entry['search_result']}")
                if entry.get("query"):
                    lines.append(f"[ACT web_search] query: {entry['query']}")
            elif action == "fetch_webpage":
                if entry.get("page_content"):
                    lines.append(f"[ACT fetch_webpage] page_content:\n{entry['page_content']}")
                if entry.get("url"):
                    lines.append(f"[ACT fetch_webpage] url: {entry['url']}")
            elif action == "explore_mcp":
                if entry.get("selected_tools") is not None:
                    lines.append(f"[ACT explore_mcp] selected_tools: {json.dumps(entry['selected_tools'], ensure_ascii=False)}")
                if entry.get("explore_plan"):
                    lines.append(f"[ACT explore_mcp] explore_plan:\n{entry['explore_plan']}")
            elif action == "exe_mcp":
                if entry.get("results"):
                    for r in entry["results"]:
                        srv = r.get("server", "")
                        tool = r.get("tool", "")
                        if r.get("error"):
                            lines.append(f"[ACT exe_mcp] {srv}/{tool} error: {r['error']}")
                        elif r.get("result"):
                            lines.append(f"[ACT exe_mcp] {srv}/{tool} result:\n{json.dumps(r['result'], ensure_ascii=False)}")
                if entry.get("display_content"):
                    lines.append(f"[ACT exe_mcp] result:\n{entry['display_content']}")
                if entry.get("error"):
                    lines.append(f"[ACT exe_mcp] error: {entry['error']}")
            elif action == "select_images":
                for item in entry.get("selected_images") or []:
                    path = item.get("path", "")
                    reason = item.get("reason", "")
                    lines.append(f"[ACT select_images] {path}: {reason}")
            else:
                if entry.get("search_result"):
                    lines.append(f"[ACT {action}] search_result:\n{entry['search_result']}")
        elif entry_type == "observe":
            action = entry.get("action", "")
            content = entry.get("content", "")
            lines.append(f"[OBSERVE] content:\n{json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else content}")
    return "\n".join(lines)