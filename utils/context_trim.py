import json
from typing import List, Optional

from data_access.observe_log import save_session_context


FRONTEND_ACTIONS = {"output_text", "ask_question", "ask_choice", "summary_and_pause", "attempt_completion"}


def parse_json_raw(raw: str) -> dict:
    raw = raw.strip()
    for prefix in ('```json', '```'):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
    for suffix in ('```',):
        if raw.endswith(suffix):
            raw = raw[:-len(suffix)]
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}

HISTORY_RETENTION = {
    "think": 3,
    "action": 3,
    "act_code": 1,
    "act_result": 999,
    "act_error": 1,
    "act_explore_db": 999,
    "act_explore_func": 999,
    "act_search_result": 3,
    "act_solved": 999,
    "act_output_text": 999,
    "act_ask_question": 999,
    "act_ask_choice": 999,
    "act_summary_and_pause": 999,
    "act_attempt_completion": 999,
    "act_generate_document": 1,
    "observe": 3,
    "observe_explore_schema": 3,
    "observe_explore_functions": 3,
    "observe_generate_and_execute": 3,
    "observe_output_text": 3,
    "observe_ask_question": 3,
    "observe_ask_choice": 3,
    "observe_summary_and_pause": 3,
    "observe_attempt_completion": 3,
}


def _get_entry_category(entry: dict) -> Optional[str]:
    role = entry.get("role", "")
    entry_type = entry.get("type", "")
    if role == "user":
        return None
    if entry_type == "think":
        return "think"
    if entry_type == "action_decision":
        return "action"
    if entry_type == "act":
        action = entry.get("action", "")
        if action == "explore_schema":
            return "act_explore_db"
        if action == "explore_functions":
            return "act_explore_func"
        if action == "generate_and_execute":
            if entry.get("code"):
                return "act_code"
            if entry.get("error"):
                return "act_error"
            return "act_result"
        if action == "solved":
            return "act_solved"
        if action == "generate_document":
            return "act_generate_document"
        if action in FRONTEND_ACTIONS:
            return f"act_{action}"
        return "act_search_result"
    if entry_type == "observe":
        action = entry.get("action", "")
        if action:
            return f"observe_{action}"
        return "observe"
    return None


def _get_retention_limit(category: str) -> Optional[int]:
    if category in HISTORY_RETENTION:
        return HISTORY_RETENTION[category]
    if category.startswith("observe_"):
        return HISTORY_RETENTION.get("observe")
    if category.startswith("act_"):
        return HISTORY_RETENTION.get("act_search_result")
    return None


def trim_conversation_history(history: List[dict]) -> List[dict]:
    keep_indices = set()
    from_end_counts = {}

    for i in range(len(history) - 1, -1, -1):
        cat = _get_entry_category(history[i])
        if cat is None:
            keep_indices.add(i)
            continue

        limit = _get_retention_limit(cat)
        if limit is None:
            keep_indices.add(i)
            continue

        from_end_counts[cat] = from_end_counts.get(cat, 0) + 1
        if from_end_counts[cat] <= limit:
            keep_indices.add(i)

    return [history[i] for i in sorted(keep_indices)]


def prepare_trimmed_context(session_id: str, conversation_history: Optional[List[dict]]) -> List[dict]:
    history = conversation_history or []
    trimmed = trim_conversation_history(history)
    return trimmed


def save_session_step(session_id: str, conversation_history: Optional[List[dict]], new_entries: List[dict]) -> List[dict]:
    history = list(conversation_history or [])
    history.extend(new_entries)
    trimmed = trim_conversation_history(history)
    if session_id:
        save_session_context(session_id, history, trimmed)
    return history
