from typing import List, Dict, Optional

import requests

SEARCH_API = 'https://nominatim.openstreetmap.org/search'
USER_AGENT = "data-copilot-osm-search/1.0 (OpenStreetMap geocoding; contact: local tool)"


def search_osm_func(
        query: str,
        limit: int = 5,
        countrycodes: Optional[str] = None,
) -> List[Dict]:
    """Search an address, place name or postal code on OpenStreetMap via Nominatim.

    Returns a list of dicts with 'name', 'address' (display name), 'lat', 'lon'
    and 'url' (permalink to the place on openstreetmap.org). Returns an empty
    list when nothing resolves.
    """
    params = {
        'q': query,
        'format': 'jsonv2',
        'limit': limit,
    }
    if countrycodes:
        params['countrycodes'] = countrycodes
    try:
        resp = requests.get(SEARCH_API, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
    except requests.RequestException:
        return []
    if resp.status_code != 200:
        return []
    data = resp.json()
    if not isinstance(data, list):
        return []

    results = []
    for item in data:
        try:
            lat = float(item.get('lat'))
            lon = float(item.get('lon'))
        except (TypeError, ValueError):
            continue
        url = item.get('url') or (
            f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}"
            f"#map=17/{lat:.6f}/{lon:.6f}"
        )
        results.append({
            'name': item.get('name') or item.get('display_name'),
            'address': item.get('display_name'),
            'lat': lat,
            'lon': lon,
            'url': url,
        })
    return results
