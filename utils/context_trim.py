from typing import Callable, Iterator, List, Optional, Tuple

from data_access.observe_log import save_session_context
from utils.json_parse import parse_json
from utils.blackboard import is_blackboard_entry


FRONTEND_ACTIONS = {"ask_question", "ask_choice", "summary_and_pause", "attempt_completion"}


def parse_json_raw(raw: str) -> dict:
    result = parse_json(raw)
    return result if result is not None else {}

HISTORY_RETENTION = {
    "think": 3,                        # think 阶段 LLM 输出的分析计划
    "action": 3,                       # action 阶段 LLM 输出的动作决策
    "act_code": 1,                     # generate_and_execute 生成的代码（仅保留最近1条）
    "act_result": 999,                 # generate_and_execute 的执行结果（永久保留）
    "act_error": 1,                    # generate_and_execute 的执行错误（仅保留最近1条）
    "act_explore_db": 3,             # explore_schema 的数据库结构搜索结果
    "act_explore_func": 3,           # explore_functions 的函数目录搜索结果
    "act_explore_base_knowledge": 3, # explore_base_knowledge 的基础知识搜索结果
    "act_explore_mcp": 3,  # explore_mcp 的 MCP 工具列表
    "act_web_search": 3,               # web_search 的搜索结果
    "act_fetch_webpage": 3,            # fetch_webpage 的页面内容
    "act_exe_mcp": 999,                  # exe_mcp 的执行结果
    "act_select_images": 3,              # select_images 的选中图片列表
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
    "observe_ask_question": 3,         # ask_question 后的 observe 结果
    "observe_ask_choice": 3,           # ask_choice 后的 observe 结果
    "observe_summary_and_pause": 3,    # summary_and_pause 后的 observe 结果
    "observe_attempt_completion": 3,   # attempt_completion 后的 observe 结果
    "observe_default": 5,             # 未匹配 action 的 observe 默认保留轮数
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
        if action == "explore_mcp":
            return "act_explore_mcp"
        if action == "exe_mcp":
            return "act_exe_mcp"
        if action == "select_images":
            return "act_select_images"
        if action in FRONTEND_ACTIONS:
            return f"act_{action}"
        return "act_default"
    if entry_type == "observe":
        action = entry.get("action", "")
        if action:
            return f"observe_{action}"
        return "observe_default"
    return None


# level 1..4 -> (cap, factor): the effective per-category retention limit becomes
# ``min(base_limit, cap, round(base_limit * factor))``, but never below 1.
_CONTEXT_TRIM_LEVELS = {
    1: (50, 0.5),
    2: (12, 0.25),
    3: (4, 0.1),
    4: (1, 0.0),
}
MAX_CONTEXT_TRIM_LEVEL = max(_CONTEXT_TRIM_LEVELS)


def _get_retention_limit(category: str, level: int = 0) -> Optional[int]:
    if category in HISTORY_RETENTION:
        base = HISTORY_RETENTION[category]
    elif category.startswith("observe_"):
        base = HISTORY_RETENTION.get("observe_default")
    elif category.startswith("act_"):
        base = HISTORY_RETENTION.get("act_default")
    else:
        return None
    if base is None or level <= 0:
        return base
    cap, factor = _CONTEXT_TRIM_LEVELS.get(level, _CONTEXT_TRIM_LEVELS[MAX_CONTEXT_TRIM_LEVEL])
    effective = max(1, int(base * factor + 0.5))
    return min(base, cap, effective)


def trim_conversation_history(history: List[dict], level: int = 0) -> List[dict]:
    keep_indices = set()
    from_end_counts = {}

    for i in range(len(history) - 1, -1, -1):
        if is_blackboard_entry(history[i]):
            continue
        cat = _get_entry_category(history[i])
        if cat is None:
            keep_indices.add(i)
            continue

        limit = _get_retention_limit(cat, level)
        if limit is None:
            keep_indices.add(i)
            continue

        from_end_counts[cat] = from_end_counts.get(cat, 0) + 1
        if from_end_counts[cat] <= limit:
            keep_indices.add(i)

    return [history[i] for i in sorted(keep_indices)]


def prepare_trimmed_context(session_id: str, conversation_history: Optional[List[dict]],
                            level: int = 0) -> List[dict]:
    history = conversation_history or []
    trimmed = trim_conversation_history(history, level=level)
    return trimmed


# ---------------------------------------------------------------------------
# Context-length overflow handling
# ---------------------------------------------------------------------------
#
# When an LLM request exceeds the model's maximum context, we retry a few times
# with a progressively more aggressively trimmed context.  Levels above 0 apply
# only to the request that is about to be sent: the extra trimming is kept in
# memory and is never written back to the session history (``save_session_step``
# keeps storing the level-0 result).

_CONTEXT_ERROR_KEYWORDS = (
    "context_length", "context length", "context window",
    "maximum context", "max context", "maximum number of tokens",
    "too many tokens", "token limit", "tokens exceed", "reduce the length",
    "prompt is too long", "input is too long", "request too large",
    "exceeds the maximum", "length limit",
    "上下文长度", "上下文过长", "超过最大", "输入过长", "长度超",
)

# Per-level character cap used to shrink individual structured prompt sections
# (function catalog, DB schema, knowledge, data samples, ...) during a retry.
_LEVEL_CHAR_CAP = {0: None, 1: 80000, 2: 40000, 3: 16000, 4: 6000}


def cap_text(text: str, level: int, base_cap: Optional[int] = None) -> str:
    """Truncate a prompt section to a level-dependent character budget.

    ``level <= 0`` returns ``text`` unchanged.  ``base_cap`` lowers the cap for
    a specific section (e.g. a data sample that should stay small).
    """
    cap = _LEVEL_CHAR_CAP.get(level, _LEVEL_CHAR_CAP[max(_LEVEL_CHAR_CAP)])
    if base_cap is not None:
        cap = base_cap if cap is None else min(base_cap, cap)
    if cap and isinstance(text, str) and len(text) > cap:
        return text[:cap] + "\n...[truncated]"
    return text


def is_context_length_error(exc: Optional[BaseException]) -> bool:
    """Best-effort detection of an "input exceeds maximum context" API error."""
    if exc is None:
        return False
    parts = [str(exc)]
    for attr in ("message", "body", "code"):
        value = getattr(exc, attr, None)
        if value:
            parts.append(str(value))
    text = " ".join(parts)
    low = text.lower()
    for keyword in _CONTEXT_ERROR_KEYWORDS:
        if keyword.isascii():
            if keyword in low:
                return True
        elif keyword in text:
            return True
    return False


def _call_llm_stream_with_reasoning(prompt: str, llm, images=None):
    from agent.tools.copilot.utils.call_llm_test import call_llm_stream_with_reasoning
    return call_llm_stream_with_reasoning(prompt, llm, images=images)


def _warn_context_retry(level: int, prev_len: int, next_len: int, exc: BaseException) -> None:
    print(
        f"[WARNING] LLM context length exceeded; retrying with trim level "
        f"{level}/{MAX_CONTEXT_TRIM_LEVEL} (prompt {prev_len} -> {next_len} chars). "
        f"detail: {exc}"
    )


def stream_with_context_retry(build_prompt: Callable[[int], str], llm, images=None,
                              max_level: int = MAX_CONTEXT_TRIM_LEVEL,
                              on_retry: Optional[Callable[[int, BaseException], None]] = None
                              ) -> Iterator[Tuple[Optional[str], Optional[str]]]:
    """Stream LLM output, re-trimming the context and retrying on overflow.

    ``build_prompt(level)`` must return the full prompt for the given trim level.
    The extra trimming is transient: callers keep persisting the level-0 history.
    """
    level = 0
    prompt = build_prompt(level)
    while True:
        try:
            yield from _call_llm_stream_with_reasoning(prompt, llm, images=images)
            return
        except Exception as exc:  # noqa: BLE001 - classified below
            if level >= max_level or not is_context_length_error(exc):
                raise
            next_prompt = build_prompt(level + 1)
            if len(next_prompt) >= len(prompt):
                raise
            _warn_context_retry(level + 1, len(prompt), len(next_prompt), exc)
            level += 1
            prompt = next_prompt
            if on_retry is not None:
                on_retry(level, exc)


def call_with_context_retry(build_prompt: Callable[[int], str], llm, images=None,
                            max_level: int = MAX_CONTEXT_TRIM_LEVEL,
                            on_retry: Optional[Callable[[int, BaseException], None]] = None):
    """Non-streaming counterpart of :func:`stream_with_context_retry`."""
    from agent.tools.copilot.utils.call_llm_test import call_llm
    level = 0
    prompt = build_prompt(level)
    while True:
        try:
            return call_llm(prompt, llm, images=images)
        except Exception as exc:  # noqa: BLE001 - classified below
            if level >= max_level or not is_context_length_error(exc):
                raise
            next_prompt = build_prompt(level + 1)
            if len(next_prompt) >= len(prompt):
                raise
            _warn_context_retry(level + 1, len(prompt), len(next_prompt), exc)
            level += 1
            prompt = next_prompt
            if on_retry is not None:
                on_retry(level, exc)


def save_session_step(session_id: str, conversation_history: Optional[List[dict]], new_entries: List[dict]) -> List[dict]:
    history = list(conversation_history or [])
    history.extend(new_entries)
    trimmed = trim_conversation_history(history)
    if session_id:
        save_session_context(session_id, history, trimmed)
    return history
