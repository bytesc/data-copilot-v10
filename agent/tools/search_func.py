from typing import Optional, List

from .get_function_info import FUNCTION_DICT


FUNC_CATEGORIES = {
    "Database": ["exe_sql"],
    "Data Loading": ["load_data"],
    "Visualization": ["get_save_image_path"],
    "Web Search": ["search_web", "fetch_webpage"],
}

FUNC_EXTRA = {
    "exe_sql": {
        "usage": "Execute raw SQL queries directly against the database. Use this to fetch, filter, join, and aggregate data.",
        "signature": "exe_sql(sql: str) -> pd.DataFrame",
        "params": "- **sql** (str): A valid SQL query string (SELECT, JOIN, GROUP BY, etc.)",
        "returns": "A pandas DataFrame containing the query results.",
        "example": "exe_sql('SELECT name, age FROM users WHERE age > 25 ORDER BY age DESC')",
    },
    "load_data": {
        "usage": "Load data from a CSV file URL. Used to retrieve previously saved or processed data.",
        "signature": "load_data(url: str) -> pd.DataFrame",
        "params": "- **url** (str): URL to a CSV file (e.g. http://127.0.0.1:8009/tmp_imgs/xxx.csv)",
        "returns": "A pandas DataFrame containing the CSV data.",
        "example": "load_data('http://127.0.0.1:8009/tmp_imgs/imqtzywu.csv')",
    },
    "get_save_image_path": {
        "usage": "Generate a unique file path for saving a plot/graph image. Must be called before saving any matplotlib figure.",
        "signature": "get_save_image_path() -> str",
        "params": "*(no parameters)*",
        "returns": "A unique `.png` file path string for saving the generated graph.",
        "example": "path = get_save_image_path()  # e.g. './tmp_imgs/abc123.png'\nplt.savefig(path)",
    },
    "search_web": {
        "usage": "Search the web using DuckDuckGo and return results. Use when the database does not contain the needed information.",
        "signature": "search_web(query: str, num_results: int = 5) -> list",
        "params": "- **query** (str): Search query string\n- **num_results** (int): Number of results to return (default 5)",
        "returns": "A list of search result dictionaries with title, url, and snippet.",
        "example": "search_web('latest GDP data China 2025')",
    },
    "fetch_webpage": {
        "usage": "Fetch and extract text content from a webpage URL. Use after search_web to get detailed information.",
        "signature": "fetch_webpage(url: str) -> str",
        "params": "- **url** (str): The full URL of the webpage to fetch",
        "returns": "The extracted text content of the webpage.",
        "example": "fetch_webpage('https://example.com/article')",
    },
}


def get_func_catalog_markdown() -> str:
    lines = ["## Available Functions", ""]
    lines.append("These functions are available for use in generated code. The agent can call them to interact with the database, load data, create visualizations, and search the web.")
    lines.append("")

    for category, func_names in FUNC_CATEGORIES.items():
        lines.append(f"### {category}")
        lines.append("")
        for fname in func_names:
            func = FUNCTION_DICT.get(fname)
            if not func:
                continue
            doc = func.__doc__
            doc_lines = doc.splitlines()
            signature = doc_lines[0].strip() if doc_lines else fname
            purpose = doc_lines[1].strip() if len(doc_lines) > 1 else ''
            lines.append(f"#### `{fname}`")
            lines.append("")
            lines.append(f"```\n{signature}\n```")
            lines.append("")
            if purpose:
                lines.append(purpose)
                lines.append("")
            extra = FUNC_EXTRA.get(fname, {})
            if extra.get('example'):
                lines.append("**Example:**")
                lines.append(f"```python\n{extra.get('example')}\n```")
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
            purpose = doc_lines[1].strip() if len(doc_lines) > 1 else ''
            if len(purpose) > 80:
                purpose = purpose[:77] + '...'
            lines.append(f"| `{fname}` | {category} | {purpose} |")

    lines.append("")
    lines.append("Use `search_func` to get full documentation for all functions.")
    return "\n".join(lines)


def get_func_docs_for(fnames: List[str]) -> str:
    lines = ["## Selected Functions", ""]
    for fname in fnames:
        func = FUNCTION_DICT.get(fname)
        if not func:
            continue
        doc = func.__doc__
        doc_lines = doc.splitlines()
        signature = doc_lines[0].strip() if doc_lines else fname
        purpose = doc_lines[1].strip() if len(doc_lines) > 1 else ''
        lines.append(f"#### `{fname}`")
        lines.append("")
        lines.append(f"```\n{signature}\n```")
        lines.append("")
        if purpose:
            lines.append(purpose)
            lines.append("")
        extra = FUNC_EXTRA.get(fname, {})
        if extra.get('example'):
            lines.append("**Example:**")
            lines.append(f"```python\n{extra.get('example')}\n```")
            lines.append("")
    return "\n".join(lines)


def search_func_by_keyword(keyword: str) -> str:
    kw_lower = keyword.lower()
    keywords = [k for k in kw_lower.split() if k]
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
        doc = func.__doc__
        doc_lines = doc.splitlines()
        signature = doc_lines[0].strip() if doc_lines else fname
        purpose = doc_lines[1].strip() if len(doc_lines) > 1 else ''
        lines.append(f"### `{fname}`")
        lines.append("")
        lines.append(f"```\n{signature}\n```")
        lines.append("")
        if purpose:
            lines.append(purpose)
            lines.append("")
        extra = FUNC_EXTRA.get(fname, {})
        if extra.get('example'):
            lines.append("**Example:**")
            lines.append(f"```python\n{extra.get('example')}\n```")
            lines.append("")

    return "\n".join(lines)