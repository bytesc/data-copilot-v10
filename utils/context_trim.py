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
    "act_fetch_webpage": 5,            # fetch_webpage 的页面内容（一次可并行多页）
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
            # The execution result (and error) is kept nearly permanently, while
            # the generated code is heavy and trimmed on its own; classify by
            # result/error first so a result-bearing entry is not demoted to the
            # short-lived "act_code" bucket. A successful run may have an empty
            # result (no textual output), so also treat `exec_ok` as a result so
            # such entries are kept instead of being trimmed as code-only.
            if entry.get("error"):
                return "act_error"
            if entry.get("result") or entry.get("exec_ok"):
                return "act_result"
            if entry.get("code"):
                return "act_code"
            return "act_default"
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


_GENERATE_ACTION = "generate_and_execute"


def _strip_generated_code(entry: dict) -> dict:
    """Return a copy of a generate_and_execute entry without its heavy ``code``.

    ``code`` and the execution result share one history entry, so the result is
    kept permanently while the generated code is only retained for the most
    recent ``act_code`` window. Older entries keep their result but lose the
    code, instead of being dropped entirely.
    """
    if entry.get("action") != _GENERATE_ACTION or "code" not in entry:
        return entry
    stripped = dict(entry)
    stripped.pop("code", None)
    return stripped


def trim_conversation_history(history: List[dict], level: int = 0) -> List[dict]:
    keep_indices = set()
    from_end_counts = {}

    # Generated code shares its entry with the permanently-kept execution
    # result, so its retention is enforced by stripping the ``code`` field from
    # older entries rather than dropping the whole entry (which would also lose
    # the result). The result/error classifications are counted separately.
    code_limit = _get_retention_limit("act_code", level)
    code_seen = 0
    strip_code_indices = set()

    for i in range(len(history) - 1, -1, -1):
        entry = history[i]
        if is_blackboard_entry(entry):
            continue
        cat = _get_entry_category(entry)
        if cat is None:
            keep_indices.add(i)
            continue

        if cat in ("act_code", "act_result", "act_error") and entry.get("code"):
            code_seen += 1
            if code_limit is not None and code_seen > code_limit:
                strip_code_indices.add(i)

        limit = _get_retention_limit(cat, level)
        if limit is None:
            keep_indices.add(i)
            continue

        from_end_counts[cat] = from_end_counts.get(cat, 0) + 1
        if from_end_counts[cat] <= limit:
            keep_indices.add(i)

    trimmed = []
    for i, entry in enumerate(history):
        if i not in keep_indices:
            continue
        if i in strip_code_indices:
            entry = _strip_generated_code(entry)
        trimmed.append(entry)
    return trimmed


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

# Only phrases that specifically identify an input/context length overflow.
# Generic fragments such as "exceeds the maximum" or "length limit" were
# removed: they also match unrelated runtime errors (e.g. row/column limits),
# which made the retry-with-trimming path fire on errors that trimming cannot
# fix.
_CONTEXT_ERROR_KEYWORDS = (
    "context_length", "context length", "context window",
    "maximum context", "max context", "maximum number of tokens",
    "too many tokens", "token limit", "tokens exceed", "reduce the length",
    "prompt is too long", "input is too long", "request too large",
    "上下文长度", "上下文过长", "超过最大上下文", "输入过长", "长度超",
)

# Per-level character cap used to shrink individual structured prompt sections
# (function catalog, DB schema, knowledge, data samples, ...) during a retry.
_LEVEL_CHAR_CAP = {0: None, 1: 80000, 2: 40000, 3: 16000, 4: 6000}


def cap_text(text: str, level: int, base_cap: Optional[int] = None) -> str:
    """Truncate a prompt section to a level-dependent character budget.

    ``level <= 0`` returns ``text`` unchanged.  ``base_cap`` lowers the cap for
    a specific section (e.g. a data sample that should stay small).

    Non-``str`` inputs (e.g. the lazy ``_DynamicStr`` knowledge objects such as
    ``BASE``/``DOC``/``TARGET``) are coerced with ``str()`` first so the cap is
    actually applied. Previously the ``isinstance(text, str)`` guard silently
    skipped truncation for those objects, so the context-length retry could not
    shrink the sections that used them (notably document generation).
    """
    if not isinstance(text, str):
        text = str(text)
    cap = _LEVEL_CHAR_CAP.get(level, _LEVEL_CHAR_CAP[max(_LEVEL_CHAR_CAP)])
    if base_cap is not None:
        cap = base_cap if cap is None else min(base_cap, cap)
    if cap and len(text) > cap:
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

    Retrying is only safe while nothing has been emitted downstream yet. A
    context-length error raised at request time (before the first chunk) is
    retried with a more aggressively trimmed prompt. A context-length error
    raised *mid-stream*, after chunks were already forwarded to the consumer, is
    re-raised instead of retried: replaying the whole response after a partial
    one would duplicate the visible output and pollute the caller's accumulated
    buffers, and the concatenated fragments can no longer be reparsed reliably.
    """
    level = 0
    prompt = build_prompt(level)
    while True:
        emitted = False  # whether this attempt already yielded anything downstream
        try:
            for chunk, reasoning in _call_llm_stream_with_reasoning(prompt, llm, images=images):
                if chunk or reasoning:
                    emitted = True
                yield chunk, reasoning
            return
        except Exception as exc:  # noqa: BLE001 - classified below
            if not is_context_length_error(exc):
                raise
            if emitted:
                # Mid-stream failure: retrying would replay the full response
                # after a partial one, so propagate and let the caller surface a
                # terminal error instead of concatenating two attempts.
                raise
            if level >= max_level:
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
