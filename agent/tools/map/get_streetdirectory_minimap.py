from typing import List, Tuple, Optional, Dict, Union

import requests

SEARCH_API = 'https://www.streetdirectory.com/api/'
BASE_LOCATION_URL = 'https://www.streetdirectory.com/location/{pid}/{aid}/'
USER_AGENT = "data-copilot-streetdirectory/1.0 (StreetDirectory minimap; contact: local tool)"


def _search(query: str) -> Optional[Dict]:
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
        return None
    data = resp.json()
    if not isinstance(data, list) or len(data) < 2:
        return None
    for item in data[1:]:
        if item.get('pid') and item.get('aid'):
            return item
    return None


def get_streetdirectory_minimap_func(
        markers: Optional[List[Dict[str, Union[str, Tuple[float, float]]]]] = None,
        width: int = 480,
        height: int = 480,
) -> List[Tuple[str, str]]:
    """Generate StreetDirectory.com minimaps.

    Unlike OpenStreetMap, StreetDirectory has no public tile API, so markers are
    resolved through StreetDirectory's search API and each resolved location is
    embedded as an iframe of its official location page.

    Returns a list of (url, iframe) tuples, one per resolved marker. Markers
    that cannot be resolved to a StreetDirectory location are skipped.
    """
    if not markers:
        markers = []

    maps = []
    for marker in markers:
        location = marker.get('location')
        if location is None:
            continue
        if isinstance(location, tuple):
            query = '%.5f,%.5f' % (float(location[0]), float(location[1]))
        else:
            query = str(location).strip()
        if not query:
            continue

        item = _search(query)
        if item is None:
            continue

        url = BASE_LOCATION_URL.format(pid=item['pid'], aid=item['aid'])
        iframe = (f'<iframe src="{url}" height="{height}" width="{width}" '
                  f'scrolling="no" frameborder="0" allowfullscreen="allowfullscreen"></iframe>')
        maps.append((url, iframe))

    return maps
