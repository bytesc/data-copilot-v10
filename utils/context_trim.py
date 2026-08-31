from typing import List, Optional

from data_access.observe_log import save_session_context
from utils.json_parse import parse_json


FRONTEND_ACTIONS = {"output_text", "ask_question", "ask_choice", "summary_and_pause", "attempt_completion"}


def parse_json_raw(raw: str) -> dict:
    result = parse_json(raw)
    return result if result is not None else {}

HISTORY_RETENTION = {
    "think": 3,                        # think 阶段 LLM 输出的分析计划
    "action": 3,                       # action 阶段 LLM 输出的动作决策
    "act_code": 1,                     # generate_and_execute 生成的代码（仅保留最近1条）
    "act_result": 999,                 # generate_and_execute 的执行结果（永久保留）
    "act_error": 1,                    # generate_and_execute 的执行错误（仅保留最近1条）
    "act_explore_db": 999,             # explore_schema 的数据库结构搜索结果（永久保留）
    "act_explore_func": 999,           # explore_functions 的函数目录搜索结果（永久保留）
    "act_explore_base_knowledge": 999, # explore_base_knowledge 的基础知识搜索结果（永久保留）
    "act_web_search": 3,               # web_search 的搜索结果
    "act_fetch_webpage": 3,            # fetch_webpage 的页面内容
    "act_output_text": 999,            # output_text 动作的输出文本（永久保留）
    "act_ask_question": 999,           # ask_question 动作的提问内容（永久保留）
    "act_ask_choice": 999,             # ask_choice 动作的选择项（永久保留）
    "act_summary_and_pause": 999,      # summary_and_pause 动作的进度摘要（永久保留）
    "act_attempt_completion": 999,     # attempt_completion 动作的最终结果（永久保留）
    "act_generate_document": 1,        # generate_document 生成的文档（仅保留最近1条）
    "act_default": 999,  # 未匹配的 action 默认保留轮数
    "observe_explore_schema": 3,       # explore_schema 后的 observe 结果
    "observe_explore_functions": 3,    # explore_functions 后的 observe 结果
    "observe_explore_base_knowledge": 3, # explore_base_knowledge 后的 observe 结果
    "observe_generate_and_execute": 3, # generate_and_execute 后的 observe 结果
    "observe_output_text": 3,          # output_text 后的 observe 结果
    "observe_ask_question": 3,         # ask_question 后的 observe 结果
    "observe_ask_choice": 3,           # ask_choice 后的 observe 结果
    "observe_summary_and_pause": 3,    # summary_and_pause 后的 observe 结果
    "observe_attempt_completion": 3,   # attempt_completion 后的 observe 结果
    "observe_default": 999,             # 未匹配 action 的 observe 默认保留轮数
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
        if action == "explore_base_knowledge":
            return "act_explore_base_knowledge"
        if action == "generate_and_execute":
            if entry.get("code"):
                return "act_code"
            if entry.get("error"):
                return "act_error"
            return "act_result"
        if action == "generate_document":
            return "act_generate_document"
        if action == "web_search":
            return "act_web_search"
        if action == "fetch_webpage":
            return "act_fetch_webpage"
        if action in FRONTEND_ACTIONS:
            return f"act_{action}"
        return "act_default"
    if entry_type == "observe":
        action = entry.get("action", "")
        if action:
            return f"observe_{action}"
        return "observe_default"
    return None


def _get_retention_limit(category: str) -> Optional[int]:
    if category in HISTORY_RETENTION:
        return HISTORY_RETENTION[category]
    if category.startswith("observe_"):
        return HISTORY_RETENTION.get("observe_default")
    if category.startswith("act_"):
        return HISTORY_RETENTION.get("act_default")
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
