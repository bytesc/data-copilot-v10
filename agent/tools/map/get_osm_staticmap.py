import io
import math
from typing import List, Tuple, Optional, Dict, Union

import requests
from PIL import Image, ImageDraw, ImageFont

TILE_SIZE = 256
MAX_ZOOM = 19
USER_AGENT = "data-copilot-staticmap/1.0 (OpenStreetMap static map; contact: local tool)"
TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

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


def _parse_color(color, default=(0, 0, 0, 255)):
    if color is None:
        return default
    if isinstance(color, (tuple, list)):
        if len(color) == 3:
            return (int(color[0]), int(color[1]), int(color[2]), 255)
        return tuple(int(c) for c in color)
    s = str(color).strip()
    if s.startswith('#'):
        s = s[1:]
        if len(s) == 6:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255)
        return default
    parts = s.split(',')
    if len(parts) == 3:
        return (int(parts[0].strip()), int(parts[1].strip()), int(parts[2].strip()), 255)
    return default


def _lat_lng_to_global_px(lat: float, lng: float, zoom: int) -> Tuple[float, float]:
    n = 2 ** zoom
    x = (lng + 180.0) / 360.0 * n * TILE_SIZE
    lat_rad = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n * TILE_SIZE
    return x, y


def _fetch_tile(x: int, y: int, z: int) -> Image.Image:
    url = TILE_URL.format(z=z, x=x, y=y)
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"OSM tile request failed with status {resp.status_code}: {resp.content[:200]}")
    return Image.open(io.BytesIO(resp.content)).convert("RGBA")


def _compose_base(latitude: float, longitude: float, zoom: int, width: int, height: int):
    n = 2 ** zoom
    cx, cy = _lat_lng_to_global_px(latitude, longitude, zoom)
    left_px = cx - width / 2.0
    top_px = cy - height / 2.0
    min_tx = int(math.floor(left_px / TILE_SIZE))
    max_tx = int(math.floor((left_px + width - 1) / TILE_SIZE))
    min_ty = int(math.floor(top_px / TILE_SIZE))
    max_ty = int(math.floor((top_px + height - 1) / TILE_SIZE))

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for ty in range(min_ty, max_ty + 1):
        if ty < 0 or ty >= n:
            continue
        for tx in range(min_tx, max_tx + 1):
            tile = _fetch_tile(tx % n, ty, zoom)
            dest_x = int(tx * TILE_SIZE - left_px)
            dest_y = int(ty * TILE_SIZE - top_px)
            canvas.paste(tile, (dest_x, dest_y))
    return canvas, left_px, top_px


def _project(lat: float, lng: float, zoom: int, left_px: float, top_px: float):
    gx, gy = _lat_lng_to_global_px(lat, lng, zoom)
    return gx - left_px, gy - top_px


def _draw_attribution(draw: ImageDraw.ImageDraw, width: int, height: int):
    text = "© OpenStreetMap contributors"
    try:
        font = ImageFont.load_default(10)
    except TypeError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    margin = 4
    draw.rectangle((width - text_w - 2 * margin - 2, height - text_h - margin - 1, width - 1, height - 1),
                   fill=(255, 255, 255, 200))
    draw.text((width - text_w - margin - 1, height - text_h - margin), text,
              fill=(0, 0, 0, 255), font=font)


def _draw_markers(draw: ImageDraw.ImageDraw, markers, zoom: int, left_px: float, top_px: float):
    for mk in markers:
        loc = mk.get('location')
        if not isinstance(loc, tuple):
            continue
        x, y = _project(float(loc[0]), float(loc[1]), zoom, left_px, top_px)
        color = _parse_color(COLOR_MAP.get(mk.get('color', 'red'), '#e74c3c'))
        r = 8
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color, outline=(255, 255, 255, 255), width=2)
        draw.ellipse((x - 2.5, y - 2.5, x + 2.5, y + 2.5), fill=(255, 255, 255, 255))


def _draw_polygons(draw: ImageDraw.ImageDraw, polygons, polygon_color, fillColor, zoom, left_px, top_px):
    outline = _parse_color(polygon_color, (0, 0, 0, 255))
    fill = _parse_color(fillColor) if fillColor is not None else None
    for poly in polygons:
        pts = [_project(float(p[0]), float(p[1]), zoom, left_px, top_px) for p in poly]
        if len(pts) < 3:
            continue
        if fill is not None:
            draw.polygon(pts, fill=fill)
        draw.line(pts + [pts[0]], fill=outline, width=2)


def _draw_lines(draw: ImageDraw.ImageDraw, lines, line_color, color, line_thickness, zoom, left_px, top_px):
    lc = _parse_color(line_color or color, (0, 0, 0, 255))
    width = max(1, int(line_thickness) if line_thickness else 3)
    for line in lines:
        pts = [_project(float(p[0]), float(p[1]), zoom, left_px, top_px) for p in line]
        if len(pts) < 2:
            continue
        draw.line(pts, fill=lc, width=width)


def _draw_points(draw: ImageDraw.ImageDraw, points, points_color, zoom, left_px, top_px):
    color = _parse_color(points_color, (255, 0, 0, 255))
    r = 4
    for pt in points:
        x, y = _project(float(pt[0]), float(pt[1]), zoom, left_px, top_px)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color)


def get_osm_static_map_func(
    latitude: float,
    longitude: float,
    zoom: int = 15,
    width: int = 512,
    height: int = 512,
    markers: Optional[List[Dict[str, Union[str, Tuple[float, float]]]]] = None,
    polygons: Optional[List[List[Tuple[float, float]]]] = None,
    polygon_color: Optional[str] = None,
    lines: Optional[List[List[Tuple[float, float]]]] = None,
    line_color: Optional[str] = None,
    line_thickness: Optional[int] = None,
    points: Optional[List[Tuple[float, float]]] = None,
    points_color: Optional[Union[Tuple[int, int, int], str]] = None,
    color: Optional[str] = None,
    fillColor: Optional[str] = None,
) -> bytes:
    """Generate a static OpenStreetMap PNG image centered at a location.

    Downloads OSM tiles, stitches them into a single PNG, and draws optional
    markers, polygons, lines, and points overlays on top. Returns the PNG bytes.
    """
    if latitude is None or longitude is None:
        raise ValueError("latitude and longitude are required")
    zoom = max(0, min(int(zoom), MAX_ZOOM))
    width = max(1, min(int(width), 2048))
    height = max(1, min(int(height), 2048))

    canvas, left_px, top_px = _compose_base(latitude, longitude, zoom, width, height)
    draw = ImageDraw.Draw(canvas)

    if markers:
        _draw_markers(draw, markers, zoom, left_px, top_px)
    if polygons:
        _draw_polygons(draw, polygons, polygon_color, fillColor, zoom, left_px, top_px)
    if lines:
        _draw_lines(draw, lines, line_color, color, line_thickness, zoom, left_px, top_px)
    if points:
        _draw_points(draw, points, points_color, zoom, left_px, top_px)

    _draw_attribution(draw, width, height)

    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()
