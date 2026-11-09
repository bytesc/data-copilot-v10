"""Blackboard storage for exploration results.

The blackboard lives inside the conversation history JSON as a single
``{"role": "system", "type": "blackboard", ...}`` entry.  Large search
results produced by ``explore_schema`` / ``explore_functions`` /
``explore_base_knowledge`` / ``explore_mcp`` and the images selected by
``select_images`` are written into their own region instead of the individual
act entries, so the LLM context only keeps parameters, plans and selected
identifiers.  Code generation reads the regions back when needed.
"""

import json
from typing import Any, Dict, List, Optional

BLACKBOARD_TYPE = "blackboard"

SCHEMA = "schema"
FUNCTIONS = "functions"
KNOWLEDGE = "knowledge"
MCP = "mcp"
RECENT_GENERATED_IMAGES = "rencent_generated_images"
LEGACY_IMAGES = "images"
SELECTED_IMAGES = "selected_images"

REGIONS = (SCHEMA, FUNCTIONS, KNOWLEDGE, MCP, RECENT_GENERATED_IMAGES, SELECTED_IMAGES)

ACTION_REGION_MAP = {
    "explore_schema": SCHEMA,
    "explore_functions": FUNCTIONS,
    "explore_base_knowledge": KNOWLEDGE,
    "explore_mcp": MCP,
    "select_images": SELECTED_IMAGES,
}


def empty_blackboard() -> Dict[str, Dict[str, Any]]:
    return {region: {} for region in REGIONS}


def is_blackboard_entry(entry: Any) -> bool:
    return isinstance(entry, dict) and entry.get("type") == BLACKBOARD_TYPE


def last_act_action(history: Optional[List[dict]]) -> str:
    """Return the action of the most recent executed ``act`` history entry.

    An ``observe`` entry is created right after the ``act`` it reviews, so the
    last ``act`` entry's action identifies which action's result is being
    reviewed. Storing that action on the observe entry lets the history
    retention policy be applied per action (``observe_<action>``) instead of
    always falling back to ``observe_default``.
    """
    for entry in reversed(history or []):
        if not isinstance(entry, dict) or is_blackboard_entry(entry):
            continue
        if entry.get("type") == "act":
            action = entry.get("action")
            if isinstance(action, str) and action:
                return action
    return ""


def get_blackboard(history: Optional[List[dict]]) -> Dict[str, Dict[str, Any]]:
    """Read the current blackboard out of the conversation history."""
    board = empty_blackboard()
    for entry in history or []:
        if not is_blackboard_entry(entry):
            continue
        regions = entry.get("regions")
        if not isinstance(regions, dict):
            continue
        for region in REGIONS:
            value = regions.get(region)
            if region == RECENT_GENERATED_IMAGES and not isinstance(value, dict):
                value = regions.get(LEGACY_IMAGES)
            if isinstance(value, dict):
                board[region].update(value)
    return board


def replace_blackboard(history: Optional[List[dict]], board: Dict[str, Dict[str, Any]]) -> List[dict]:
    """Return a new history list containing exactly one blackboard entry."""
    entries = [entry for entry in (history or []) if not is_blackboard_entry(entry)]
    entries.insert(0, {"role": "system", "type": BLACKBOARD_TYPE, "regions": board})
    return entries


def normalize_selected_images(images: Any) -> List[Dict[str, str]]:
    """Normalize selected image items to ``{"path", "reason"}`` dictionaries.

    ``path`` may be a local image filename (for files saved under ``tmp_imgs``)
    or a full http(s) URL for a remote image.  Plain strings are accepted for
    robustness and become entries with an empty reason.
    """
    if not isinstance(images, list):
        return []
    normalized = []
    seen = set()
    for item in images:
        if isinstance(item, str):
            item = {"path": item, "reason": ""}
        if not isinstance(item, dict):
            continue
        path = (
            item.get("path")
            or item.get("url")
            or item.get("filename")
            or item.get("file")
            or item.get("name")
        )
        if not isinstance(path, str) or not path.strip():
            continue
        path = path.strip()
        if path in seen:
            continue
        seen.add(path)
        reason = item.get("reason") or item.get("why") or ""
        normalized.append({"path": path, "reason": str(reason).strip()})
    return normalized


def _action_region_payload(action: str, act_data: dict) -> Optional[Dict[str, Any]]:
    if action == "select_images":
        return {
            "images": normalize_selected_images(
                act_data.get("images") or act_data.get("selected_images")
            ),
        }
    if action == "explore_schema":
        # A failed parse must not overwrite the region with an empty selection;
        # keep the previous SCHEMA region (mirrors explore_functions) so later
        # code generation still has the last good table/column selection.
        if act_data.get("parse_failed"):
            return None
        return {
            "selected_fields": act_data.get("selected_fields"),
            "explore_plan": act_data.get("explore_plan", ""),
            "selected_guides": act_data.get("selected_guides", []),
            "query_guide_content": act_data.get("query_guide_content", ""),
            "schema_detail": act_data.get("schema_detail", ""),
        }
    if action == "explore_functions":
        # A failed parse must not overwrite the region with an empty selection;
        # keep the previous FUNC region so later code generation still has a
        # usable function catalog (returning None leaves history unchanged).
        if act_data.get("parse_failed"):
            return None
        return {
            "selected_functions": act_data.get("selected_functions", []),
            "explore_plan": act_data.get("explore_plan", ""),
            "func_docs": act_data.get("func_docs", ""),
        }
    if action == "explore_base_knowledge":
        # A failed parse must not overwrite the region with an empty selection;
        # keep the previous KNOWLEDGE region (mirrors explore_schema /
        # explore_functions) so later code generation still has the last good
        # selection (returning None leaves history unchanged).
        if act_data.get("parse_failed"):
            return None
        return {
            "selected_knowledge_ids": act_data.get("selected_knowledge_ids", []),
            "knowledge_content": act_data.get("knowledge_content", ""),
            "summary": act_data.get("summary", ""),
        }
    if action == "explore_mcp":
        return {
            "selected_tools": act_data.get("selected_tools", []),
            "explore_plan": act_data.get("explore_plan", ""),
            "tool_detail": act_data.get("tool_detail", ""),
            "catalog": act_data.get("catalog", ""),
        }
    return None


def update_blackboard(history: Optional[List[dict]], action: str, act_data: dict) -> List[dict]:
    """Merge one exploration result into its region and persist it in history."""
    region = ACTION_REGION_MAP.get(action)
    payload = _action_region_payload(action, act_data)
    if region is None or payload is None:
        return history if history is not None else []

    board = get_blackboard(history)
    board[region] = payload
    return replace_blackboard(history, board)


def blackboard_selected_fields(board: Dict[str, Dict[str, Any]]) -> Optional[dict]:
    fields = (board.get(SCHEMA) or {}).get("selected_fields")
    return fields if isinstance(fields, dict) else None


def blackboard_selected_functions(board: Dict[str, Dict[str, Any]]) -> Optional[List[str]]:
    funcs = (board.get(FUNCTIONS) or {}).get("selected_functions")
    return funcs if isinstance(funcs, list) else None


def update_code_images(history: Optional[List[dict]], images: Optional[List[str]]) -> List[dict]:
    """Overwrite the RECENT_GENERATED_IMAGES region with the last code execution's generated image list.

    The list (filenames of locally saved images, or full URLs for remote images)
    is rendered into the ``## Blackboard`` prompt section, so the LLM knows which
    images the last code execution produced.
    """
    if not isinstance(images, list):
        images = []
    board = get_blackboard(history)
    board[RECENT_GENERATED_IMAGES] = {"images": images}
    return replace_blackboard(history, board)


def blackboard_images(board: Dict[str, Dict[str, Any]]) -> List[str]:
    images = (board.get(RECENT_GENERATED_IMAGES) or {}).get("images")
    return images if isinstance(images, list) else []


def blackboard_images_from_history(history: Optional[List[dict]]) -> List[str]:
    """Read the images region directly from a conversation history."""
    return blackboard_images(get_blackboard(history))


def blackboard_selected_images(board: Dict[str, Dict[str, Any]]) -> List[Dict[str, str]]:
    images = (board.get(SELECTED_IMAGES) or {}).get("images")
    return images if isinstance(images, list) else []


def blackboard_input_images(board: Dict[str, Dict[str, Any]]) -> List[str]:
    """Return images for multimodal LLM input.

    The last code execution's generated images come first, followed by the
    images explicitly selected through the ``select_images`` action.
    """
    result = []
    seen = set()
    for image in blackboard_images(board):
        if image and image not in seen:
            seen.add(image)
            result.append(image)
    for item in blackboard_selected_images(board):
        path = item.get("path") if isinstance(item, dict) else None
        if path and path not in seen:
            seen.add(path)
            result.append(path)
    return result


def blackboard_input_images_from_history(history: Optional[List[dict]]) -> List[str]:
    """Read generated + selected images directly from a conversation history."""
    return blackboard_input_images(get_blackboard(history))


_REGION_LABELS = {
    SCHEMA: "DB",
    FUNCTIONS: "FUNC",
    KNOWLEDGE: "KNOWLEDGE",
    MCP: "MCP",
    RECENT_GENERATED_IMAGES: "RECENT_GENERATED_IMAGES",
    SELECTED_IMAGES: "SELECTED IMAGES",
}

_REGION_NOTES = {
    SCHEMA: "Database schema gathered by `explore_schema`: `selected_fields` lists relevant tables/columns, with schema details and query guidance. Re-running `explore_schema` overwrites this region.",
    FUNCTIONS: "Function catalog gathered by `explore_functions`: `selected_functions` lists callable function names and `func_docs` contains their documentation. Re-running `explore_functions` overwrites this region.",
    KNOWLEDGE: "Business domain knowledge gathered by `explore_base_knowledge`: selected knowledge IDs, a summary, and the full content. Re-running `explore_base_knowledge` overwrites this region.",
    MCP: "External MCP tools gathered by `explore_mcp`: selected tools, tool details, and the catalog; call them with `exe_mcp`. Re-running `explore_mcp` overwrites this region.",
    RECENT_GENERATED_IMAGES: "Images generated by the most recent code execution. They are attached automatically to the next LLM call.",
    SELECTED_IMAGES: "Images explicitly kept by `select_images` or uploaded by the user, each with a path and a reason. They stay attached to every later LLM call until the region is overwritten.",
}

_REGION_FIELDS = {
    SCHEMA: [
        ("selected_fields", True),
        ("explore_plan", False),
        ("selected_guides", True),
        ("query_guide_content", False),
        ("schema_detail", False),
    ],
    FUNCTIONS: [
        ("selected_functions", True),
        ("explore_plan", False),
        ("func_docs", False),
    ],
    KNOWLEDGE: [
        ("selected_knowledge_ids", True),
        ("summary", False),
        ("knowledge_content", False),
    ],
    MCP: [
        ("selected_tools", True),
        ("explore_plan", False),
        ("tool_detail", False),
        ("catalog", False),
    ],
    RECENT_GENERATED_IMAGES: [
        ("images", True),
    ],
    SELECTED_IMAGES: [
        ("images", True),
    ],
}

# Free-text fields that can grow very large; truncated when the context retry
# kicks in (level > 0).  The structured "selected_*" identifier fields are kept.
_BULKY_FIELDS = {
    SCHEMA: ("query_guide_content", "schema_detail"),
    FUNCTIONS: ("func_docs",),
    KNOWLEDGE: ("knowledge_content",),
    MCP: ("tool_detail", "catalog"),
}
_LEVEL_BULKY_MAX = {0: None, 1: 20000, 2: 8000, 3: 3000, 4: 1000}


def blackboard_to_text(board: Dict[str, Dict[str, Any]], level: int = 0) -> str:
    """Render all blackboard regions as a prompt-friendly text block.

    Each region starts with a ``note`` line explaining which action writes it,
    what its fields mean, and whether re-running overwrites it, so the LLM can
    understand the region even in phases that do not include action
    descriptions.  The RECENT_GENERATED_IMAGES region (last code execution's
    generated image list) and SELECTED IMAGES region (images explicitly kept by
    ``select_images`` with a one-sentence reason) are rendered as well, so the
    LLM sees both the recent images and the persistent selection.  The
    ``images`` field of the ``generate_and_execute`` act entry, however, stays
    display-only and is never included by ``history_to_text``.

    ``level`` > 0 truncates the bulky free-text fields (used by the
    context-length retry); it does not affect what is persisted.
    """
    bulky_max = _LEVEL_BULKY_MAX.get(level, _LEVEL_BULKY_MAX[max(_LEVEL_BULKY_MAX)])
    sections = []
    for region in REGIONS:
        if region not in _REGION_FIELDS:
            continue
        data = board.get(region) or {}
        bulky = _BULKY_FIELDS.get(region, ())
        lines = []
        for field, is_json in _REGION_FIELDS[region]:
            value = data.get(field)
            if value is None or value == "" or value == []:
                continue
            if is_json:
                value = json.dumps(value, ensure_ascii=False)
            elif bulky_max and field in bulky and isinstance(value, str) and len(value) > bulky_max:
                value = value[:bulky_max] + "\n...[truncated]"
            lines.append(f"{field}:\n{value}")
        if lines:
            note = _REGION_NOTES.get(region)
            if note:
                lines.insert(0, f"note: {note}")
            sections.append(f"### {_REGION_LABELS[region]}\n" + "\n".join(lines))
    return "\n\n".join(sections)


def blackboard_section(history: Optional[List[dict]], level: int = 0) -> str:
    """Return a standalone blackboard prompt section from conversation history."""
    text = blackboard_to_text(get_blackboard(history), level=level)
    if not text:
        return ""
    return "\n\n## Blackboard\n\n" + text + "\n"
