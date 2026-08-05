
import json
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser


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


def fetch_webpage(url: str, max_length: int = 10000) -> str:
    """
    fetch_webpage(url: str, max_length: int = 10000) -> str:
    Fetch a webpage and extract its text content. Returns the extracted text as a string.

    This function retrieves the HTML content of a given URL, strips out HTML tags,
    scripts, styles, and other non-content elements, and returns the plain text.
    It is useful for reading the content of a specific page discovered via search_web.

    Args:
    - url (str): The full URL of the webpage to fetch (e.g., "https://example.com/article").
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
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        req = Request(url, headers=headers)
        with urlopen(req, timeout=15) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            html = response.read().decode(charset, errors="replace")

        extractor = _HTMLTextExtractor()
        extractor.feed(html)
        text = extractor.get_text()

        if len(text) > max_length:
            text = text[:max_length] + "\n...[truncated]"

        return text

    except HTTPError as e:
        return json.dumps({
            "error": f"HTTP {e.code}: {e.reason}",
            "url": url
        }, ensure_ascii=False)
    except URLError as e:
        return json.dumps({
            "error": f"URL error: {e.reason}",
            "url": url
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "url": url
        }, ensure_ascii=False)










