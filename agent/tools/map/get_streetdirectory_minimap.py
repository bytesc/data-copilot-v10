from typing import List, Tuple, Optional, Dict

import requests

SEARCH_API = 'https://www.streetdirectory.com/api/'
BASE_LOCATION_URL = 'https://www.streetdirectory.com/location/{pid}/{aid}/'
DEFAULT_URL = 'https://www.streetdirectory.com/'
USER_AGENT = "data-copilot-streetdirectory/1.0 (StreetDirectory minimap; contact: local tool)"


def search_streetdirectory_func(query: str) -> List[Dict]:
    """Search a postal code or address on StreetDirectory.com.

    Queries StreetDirectory's search API and returns up to several matching
    results as a list of dicts, each with 'name', 'address' and 'url' (the
    official location page URL). Returns an empty list when nothing resolves.
    """
    params = {
        'mode': 'search',
        'profile': 'sd_auto',
        'country': 'sg',
        'q': query,
        'show_additional': 1,
        'output': 'json',
        'start': 0,
        'limit': 5,
        'ctype': 0,
    }
    resp = requests.get(SEARCH_API, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
    if resp.status_code != 200:
        return []
    data = resp.json()
    if not isinstance(data, list) or len(data) < 2:
        return []

    results = []
    for item in data[1:]:
        if not (item.get('pid') and item.get('aid')):
            continue
        url = BASE_LOCATION_URL.format(pid=item['pid'], aid=item['aid'])
        results.append({
            'name': item.get('v'),
            'address': item.get('i'),
            'url': url,
        })
    return results


def get_streetdirectory_minimap_from_urls(
        urls: Optional[List[str]] = None,
        width: int = 480,
        height: int = 480,
) -> List[Tuple[str, str]]:
    """Build StreetDirectory.com minimaps from already-resolved location URLs.

    Each URL is embedded as an iframe of its official location page.

    Returns a list of (url, iframe) tuples, one per URL. Empty or non-string
    entries are skipped. When no URLs are given, a default StreetDirectory
    Singapore map is returned instead.
    """
    if not urls:
        urls = []

    maps = []
    for url in urls:
        if not isinstance(url, str):
            continue
        url = url.strip()
        if not url:
            continue

        iframe = (f'<iframe src="{url}" height="{height}" width="{width}" '
                  f'scrolling="no" frameborder="0" allowfullscreen="allowfullscreen"></iframe>')
        maps.append((url, iframe))

    if not maps:
        iframe = (f'<iframe src="{DEFAULT_URL}" height="{height}" width="{width}" '
                  f'scrolling="no" frameborder="0" allowfullscreen="allowfullscreen"></iframe>')
        maps.append((DEFAULT_URL, iframe))

    return maps
