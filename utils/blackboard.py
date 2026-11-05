"""Blackboard storage for exploration results.

The blackboard lives inside the conversation history JSON as a single
``{"role": "system", "type": "blackboard", ...}`` entry.  Large search
results produced by ``explore_schema`` / ``explore_functions`` /
``explore_base_knowledge`` / ``explore_mcp`` are written into their own region
instead of the individual act entries, so the LLM context only keeps
parameters, plans and selected identifiers.  Code generation reads the regions
back when needed.
"""

from typing import Any, Dict, List, Optional

BLACKBOARD_TYPE = "blackboard"

SCHEMA = "schema"
FUNCTIONS = "functions"
KNOWLEDGE = "knowledge"
MCP = "mcp"

REGIONS = (SCHEMA, FUNCTIONS, KNOWLEDGE, MCP)

ACTION_REGION_MAP = {
    "explore_schema": SCHEMA,
    "explore_functions": FUNCTIONS,
    "explore_base_knowledge": KNOWLEDGE,
    "explore_mcp": MCP,
}


def empty_blackboard() -> Dict[str, Dict[str, Any]]:
    return {region: {} for region in REGIONS}


def is_blackboard_entry(entry: Any) -> bool:
    return isinstance(entry, dict) and entry.get("type") == BLACKBOARD_TYPE


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
            if isinstance(value, dict):
                board[region].update(value)
    return board


def replace_blackboard(history: Optional[List[dict]], board: Dict[str, Dict[str, Any]]) -> List[dict]:
    """Return a new history list containing exactly one blackboard entry."""
    entries = [entry for entry in (history or []) if not is_blackboard_entry(entry)]
    entries.insert(0, {"role": "system", "type": BLACKBOARD_TYPE, "regions": board})
    return entries


def _action_region_payload(action: str, act_data: dict) -> Optional[Dict[str, Any]]:
    if action == "explore_schema":
        return {
            "selected_fields": act_data.get("selected_fields"),
            "explore_plan": act_data.get("explore_plan", ""),
            "selected_guides": act_data.get("selected_guides", []),
            "query_guide_content": act_data.get("query_guide_content", ""),
            "schema_detail": act_data.get("schema_detail", ""),
        }
    if action == "explore_functions":
        return {
            "selected_functions": act_data.get("selected_functions", []),
            "explore_plan": act_data.get("explore_plan", ""),
            "func_docs": act_data.get("func_docs", ""),
        }
    if action == "explore_base_knowledge":
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
