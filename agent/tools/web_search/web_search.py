"""Web search and page fetching tool for the agent.

Provides web search capability using DuckDuckGo search engine,
and page content fetching using headless browser (Playwright) or plain HTTP.

Usage:
    results = search_web("latest medical research 2024")
    content = fetch_web_page("https://example.com/article")
"""

import asyncio
import json
from typing import Optional, List, Dict, Any


def search_web(query: str, max_results: int = 10, region: str = "wt-wt") -> str:
    """
    search_web(query: str, max_results: int = 10, region: str = "wt-wt") -> str:
    Search the web using DuckDuckGo search engine. Returns search results as a JSON string.

    This function performs a web search and returns results including title, URL, and snippet
    for each result. It can be used to find current information, verify facts, or discover
    relevant web pages for a given query.

    Args:
    - query (str): The search query string (e.g., "latest CRISPR gene therapy trials 2024").
    - max_results (int): Maximum number of results to return (default: 10, max: 50).
    - region (str): Search region code (default: "wt-wt" for worldwide).
      Common codes: "us-en" (US English), "cn-zh" (China Chinese), "uk-en" (UK English).

    Returns:
    - str: JSON string containing search results with the following structure:
      ```json
      {
        "query": "search query",
        "count": 10,
        "results": [
          {
            "title": "Page Title",
            "url": "https://example.com/page",
            "snippet": "Brief description of the page content..."
          }
        ]
      }
      ```
      Returns a JSON error string if search fails.

    Example:
    ```python
        results = search_web("cell therapy clinical trials phase 3")
        # Output(str): JSON string with search results
        # Parse with: import json; data = json.loads(results)

        results = search_web("mRNA vaccine cancer research", max_results=5)
        # Output(str): JSON string with top 5 results

        results = search_web("中国医药新闻", region="cn-zh")
        # Output(str): JSON string with Chinese region results
    ```
    """
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
    except ImportError:
        return json.dumps({
            "error": "ddgs not installed. Run: pip install ddgs",
            "query": query
        }, ensure_ascii=False)

    try:
        ddgs = DDGS()
        backends = ["api", "html", "lite"]
        last_error = None

        for backend in backends:
            try:
                results = list(ddgs.text(
                    query,
                    max_results=max_results,
                    region=region,
                    backend=backend,
                    timeout=30
                ))
                if results:
                    break
            except Exception:
                last_error = None
                continue
        else:
            results = []

        if not results and last_error is None:
            return json.dumps({
                "error": "All search backends (api, html, lite) failed or timed out. This is likely a network connectivity issue.",
                "query": query
            }, ensure_ascii=False)

        formatted_results = []
        for r in results:
            formatted_results.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", "")
            })

        output = {
            "query": query,
            "count": len(formatted_results),
            "results": formatted_results
        }
        return json.dumps(output, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "error": str(e),
            "query": query
        }, ensure_ascii=False)










