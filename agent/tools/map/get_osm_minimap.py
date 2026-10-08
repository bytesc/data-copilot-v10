import html
import json
from typing import List, Tuple, Optional, Dict, Union
from urllib.parse import urlencode

MAX_MARKERS_PER_MAP = 100

COLOR_MAP = {
    'red': '#e74c3c',
    'blue': '#3498db',
    'green': '#2ecc71',
    'black': '#333333',
    'yellow': '#f1c40f',
    'orange': '#e67e22',
    'purple': '#9b59b6',
    'white': '#ffffff',
    'grey': '#95a5a6',
}

DEFAULT_ICON = 'fa-map-marker'

_IFRAME_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#map{width:100%;height:100%;margin:0;padding:0}</style>
</head>
<body>
<div id="map"></div>
<script>
var MARKERS = {MARKERS_JSON};
var COLORS = {{"red":"#e74c3c","blue":"#3498db","green":"#2ecc71","black":"#333333","yellow":"#f1c40f","orange":"#e67e22","purple":"#9b59b6","white":"#ffffff","grey":"#95a5a6"}};
var map = L.map('map');
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{maxZoom:19, attribution:'&copy; OpenStreetMap contributors'}}).addTo(map);
var bounds = [];
MARKERS.forEach(function(mk){{
  var color = COLORS[mk.color] || '#e74c3c';
  var icon = L.divIcon({{
    html:'<div style="background:'+color+';width:28px;height:28px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center"><i class="fa '+(mk.icon||'fa-map-marker')+'" style="transform:rotate(45deg);color:#fff;font-size:13px"></i></div>',
    iconSize:[28,28], iconAnchor:[14,28], popupAnchor:[0,-28]
  }});
  var marker = L.marker([mk.lat, mk.lng], {{icon:icon}}).addTo(map);
  if (mk.label) marker.bindTooltip(mk.label);
  if (mk.popup) marker.bindPopup(mk.popup);
  bounds.push([mk.lat, mk.lng]);
}});
if (bounds.length > 1) {{
  map.fitBounds(bounds, {{padding:[30,30]}});
}} else if (bounds.length === 1) {{
  map.setView(bounds[0], {ZOOM});
}} else {{
  map.setView([20, 0], 3);
}}
</script>
</body>
</html>"""


def _clean_marker(mk: Dict) -> Dict:
    out = {'lat': mk['lat'], 'lng': mk['lng'], 'color': mk['color'], 'icon': mk['icon']}
    if mk.get('label'):
        out['label'] = mk['label']
    if mk.get('popup'):
        out['popup'] = mk['popup']
    return out


def _build_share_url(points: List[Dict]) -> str:
    if not points:
        params = urlencode({'bbox': '-180,-85,180,85', 'layer': 'mapnik'})
        return 'https://www.openstreetmap.org/export/embed.html?' + params

    lats = [p['lat'] for p in points]
    lngs = [p['lng'] for p in points]
    min_lat, max_lat = min(lats), max(lats)
    min_lng, max_lng = min(lngs), max(lngs)
    lat_span = max(max_lat - min_lat, 0.005)
    lng_span = max(max_lng - min_lng, 0.005)
    pad_lat = lat_span * 0.1
    pad_lng = lng_span * 0.1
    bbox = '%.5f,%.5f,%.5f,%.5f' % (
        min_lng - pad_lng, min_lat - pad_lat, max_lng + pad_lng, max_lat + pad_lat)
    params = {'bbox': bbox, 'layer': 'mapnik'}
    first = points[0]
    params['marker'] = '%.5f,%.5f' % (first['lat'], first['lng'])
    return 'https://www.openstreetmap.org/export/embed.html?' + urlencode(params)


def _build_iframe(points: List[Dict], zoom: int, width: int, height: int) -> str:
    markers_json = json.dumps([_clean_marker(p) for p in points])
    markers_json = markers_json.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    html_doc = _IFRAME_TEMPLATE.replace('{MARKERS_JSON}', markers_json).replace('{ZOOM}', str(zoom))
    srcdoc = html.escape(html_doc, quote=True)
    return (f'<iframe src="about:blank" srcdoc="{srcdoc}" height="{height}" width="{width}" '
            f'scrolling="no" frameborder="0" allowfullscreen="allowfullscreen"></iframe>')


def get_osm_minimap_func(
        markers: Optional[List[Dict[str, Union[str, Tuple[float, float]]]]] = None,
        zoom: int = 15,
        width: int = 480,
        height: int = 480,
) -> List[Tuple[str, str]]:
    """Generate OpenStreetMap minimaps.

    Returns a list of (url, iframe) tuples. The iframe embeds a Leaflet map
    with OpenStreetMap tiles and all markers; the url is a shareable
    OpenStreetMap embed link covering the markers' bounding box. Markers are
    split into chunks of at most MAX_MARKERS_PER_MAP.
    """
    if not markers:
        markers = []

    points = []
    for marker in markers:
        location = marker.get('location')
        if not isinstance(location, tuple):
            continue
        lat = float(location[0])
        lng = float(location[1])
        color = marker.get('color', 'red')
        icon = marker.get('icon') or DEFAULT_ICON
        points.append({
            'lat': lat,
            'lng': lng,
            'color': color if color in COLOR_MAP else 'red',
            'icon': icon,
            'label': marker.get('label'),
            'popup': marker.get('popup'),
        })

    chunks = [points[i:i + MAX_MARKERS_PER_MAP] for i in range(0, len(points), MAX_MARKERS_PER_MAP)] or [[]]

    maps = []
    for chunk in chunks:
        url = _build_share_url(chunk)
        iframe = _build_iframe(chunk, zoom, width, height)
        maps.append((url, iframe))

    return maps
