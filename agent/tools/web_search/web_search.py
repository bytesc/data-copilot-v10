
import json
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser

import httpx

try:
    import trafilatura
    _HAS_TRAFILATURA = True
except ImportError:
    _HAS_TRAFILATURA = False


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
        from ddgs import DDGS
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
                    timeout=15
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


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._text_parts = []
        self._skip_tags = {"script", "style", "noscript", "head", "meta", "link"}
        self._current_skip = False

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._current_skip = True

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._current_skip = False

    def handle_data(self, data):
        if not self._current_skip:
            text = data.strip()
            if text:
                self._text_parts.append(text)

    def get_text(self):
        return "\n".join(self._text_parts)


_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

DEFAULT_MAX_WORKERS = 5
MAX_URLS = 10


def _extract_text(html: str, url: str = "", max_length: int = 10000) -> str:
    """Extract the main text content of an HTML document.

    Uses trafilatura for main-content extraction (boilerplate removal) and falls
    back to the lightweight ``_HTMLTextExtractor`` when trafilatura is missing or
    returns nothing usable (e.g. non-article pages).
    """
    text = ""
    if _HAS_TRAFILATURA:
        try:
            text = trafilatura.extract(
                html,
                url=url or None,
                output_format="markdown",
                include_links=False,
                include_tables=True,
                include_comments=False,
                favor_recall=True,
            ) or ""
        except Exception:
            text = ""
    if not text.strip():
        try:
            extractor = _HTMLTextExtractor()
            extractor.feed(html)
            text = extractor.get_text()
        except Exception:
            text = ""
    if len(text) > max_length:
        text = text[:max_length] + "\n...[truncated]"
    return text


def _fetch_one(client: "httpx.Client", url: str, max_length: int) -> dict:
    """Fetch a single URL and extract its text. Never raises; returns an error field."""
    try:
        resp = client.get(url, headers=_HEADERS)
        resp.raise_for_status()
        html = resp.text
    except httpx.HTTPStatusError as e:
        return {"url": url, "content": "", "error": f"HTTP {e.response.status_code}: {e.response.reason_phrase}"}
    except httpx.HTTPError as e:
        return {"url": url, "content": "", "error": f"Request error: {e}"}
    except Exception as e:
        return {"url": url, "content": "", "error": str(e)}

    text = _extract_text(html, url=url, max_length=max_length)
    if not text.strip():
        return {"url": url, "content": "", "error": "No extractable text content found"}
    return {"url": url, "content": text, "error": None}


def fetch_webpages(urls, max_length: int = 10000, max_workers: int = DEFAULT_MAX_WORKERS) -> str:
    """
    fetch_webpages(urls, max_length: int = 10000, max_workers: int = 5) -> str:
    Fetch and extract the text content of MULTIPLE webpages in parallel.

    Args:
    - urls (list[str]): The URLs to fetch (up to 10; extra entries are dropped).
    - max_length (int): Max characters returned PER page (default 10000, capped at 50000).
    - max_workers (int): Max concurrent fetches (default 5).

    Returns:
    - str: JSON string {"count": N, "results": [{"url", "content", "error"}, ...]}.
      Results preserve the input URL order. A failing URL carries a non-null "error".
      Returns a JSON error string only when the whole batch fails.
    """
    urls = [u.strip() for u in urls if isinstance(u, str) and u.strip()][:MAX_URLS]
    if not urls:
        return json.dumps({"error": "No valid URLs provided", "results": []}, ensure_ascii=False)
    try:
        max_length = min(int(max_length), 50000)
    except (ValueError, TypeError):
        max_length = 10000

    results = [None] * len(urls)
    try:
        # httpx.Client is thread-safe and shared across the pool (one connection pool).
        # http2 stays off to avoid an extra `h2` dependency.
        with httpx.Client(follow_redirects=True, timeout=20.0, http2=False) as client:
            with ThreadPoolExecutor(max_workers=min(max_workers, len(urls))) as pool:
                futures = {pool.submit(_fetch_one, client, u, max_length): i
                           for i, u in enumerate(urls)}
                for fut in as_completed(futures):
                    i = futures[fut]
                    try:
                        results[i] = fut.result()
                    except Exception as e:
                        results[i] = {"url": urls[i], "content": "", "error": str(e)}
    except Exception as e:
        return json.dumps({"error": str(e), "results": []}, ensure_ascii=False)

    return json.dumps({"count": len(results), "results": results}, ensure_ascii=False)


def fetch_webpage(url, max_length: int = 10000) -> str:
    """
    fetch_webpage(url, max_length: int = 10000) -> str:
    Fetch a webpage and extract its text content. Returns the extracted text as a string.

    This function retrieves the HTML content of a given URL, extracts the main text
    (boilerplate/navigation removed via trafilatura), and returns it. Useful for
    reading the content of a specific page discovered via search_web.

    Args:
    - url (str | list[str]): The full URL of the webpage to fetch
      (e.g., "https://example.com/article"). A list is also accepted and delegated to
      ``fetch_webpages`` (returned as a JSON batch string).
    - max_length (int): Maximum number of characters to return (default: 10000).
      This prevents excessively long responses from large pages.

    Returns:
    - str: The extracted text content of the webpage.
      Returns a JSON error string if the fetch fails.

    Example:
    ```python
        text = fetch_webpage("https://example.com/article")
        # Output(str): Plain text content of the page

        text = fetch_webpage("https://example.com", max_length=5000)
        # Output(str): First 5000 characters of text content
    ```
    """
    if isinstance(url, (list, tuple)):
        return fetch_webpages(url, max_length=max_length)

    url = (url or "").strip()
    if not url:
        return json.dumps({"error": "No URL provided", "url": url}, ensure_ascii=False)

    raw = fetch_webpages([url], max_length=max_length)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    items = data.get("results") or []
    if not items:
        return json.dumps({"error": data.get("error", "fetch failed"), "url": url}, ensure_ascii=False)
    item = items[0]
    if item.get("error"):
        return json.dumps({"error": item["error"], "url": url}, ensure_ascii=False)
    return item.get("content", "")










