from typing import Optional, List

from .get_function_info import FUNCTION_DICT


FUNC_CATEGORIES = {
    "Database": ["exe_sql"],
    "Data Loading": ["load_data"],
    "Visualization": ["get_save_image_path"],
    "Web Search": ["search_web", "fetch_webpage"],
}


def _get_func_desc(func) -> str:
    return '\n'.join(func.__doc__.splitlines()[1:4])


def get_func_catalog_markdown() -> str:
    lines = ["## Available Functions", ""]
    lines.append("These functions are available for use in generated code. ")
    lines.append("")

    for category, func_names in FUNC_CATEGORIES.items():
        lines.append(f"### {category}")
        lines.append("")
        for fname in func_names:
            func = FUNCTION_DICT.get(fname)
            if not func:
                continue
            lines.append(f"#### `{fname}`")
            lines.append("")
            lines.append(_get_func_desc(func))
            lines.append("")
        lines.append("")

    return "\n".join(lines)


def get_func_summary_for_agent() -> str:
    lines = ["## Function Summary", ""]
    lines.append("| Function | Category | Purpose |")
    lines.append("|----------|----------|---------|")

    for category, func_names in FUNC_CATEGORIES.items():
        for fname in func_names:
            func = FUNCTION_DICT.get(fname)
            if not func:
                continue
            doc_lines = func.__doc__.splitlines()
            purpose = doc_lines[2].strip() if len(doc_lines) > 2 else ''
            if len(purpose) > 80:
                purpose = purpose[:77] + '...'
            lines.append(f"| `{fname}` | {category} | {purpose} |")

    return "\n".join(lines)


def get_func_docs_for(fnames: List[str]) -> str:
    lines = ["## Selected Functions", ""]
    for fname in fnames:
        func = FUNCTION_DICT.get(fname)
        if not func:
            continue
        lines.append(f"#### `{fname}`")
        lines.append("")
        lines.append(_get_func_desc(func))
        lines.append("")
    return "\n".join(lines)


def search_func_by_keyword(keyword: str) -> str:
    kw_lower = keyword.lower()
    keywords = [k for k in kw_lower.split(",") if k]
    results = []

    for fname, func in FUNCTION_DICT.items():
        search_text = (fname + ' ' + (func.__doc__ or '')).lower()
        if any(k in search_text for k in keywords):
            results.append(fname)

    if not results:
        return f"*(No functions found matching keyword: `{keyword}`)*"

    lines = [f"## Function Search Results for: `{keyword}`", ""]
    for fname in results:
        func = FUNCTION_DICT.get(fname)
        if not func:
            continue
        lines.append(f"### `{fname}`")
        lines.append("")
        lines.append(_get_func_desc(func))
        lines.append("")

    return "\n".join(lines)