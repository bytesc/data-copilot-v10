import http.client
from typing import Optional, List, Tuple


def get_onemap_static_map_func(
    layerchosen: str = "default",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    postal: Optional[str] = None,
    zoom: int = 15,
    width: int = 512,
    height: int = 512,
    polygons: Optional[List[List[Tuple[float, float]]]] = None,
    polygon_color: Optional[str] = None,
    lines: Optional[List[List[Tuple[float, float]]]] = None,
    line_color: Optional[str] = None,
    line_thickness: Optional[int] = None,
    points: Optional[List[Tuple[float, float]]] = None,
    points_color: Optional[Tuple[int, int, int]] = None,
    color: Optional[str] = None,
    fillColor: Optional[str] = None,
) -> bytes:
    params = {
        "layerchosen": layerchosen,
        "zoom": str(zoom),
        "width": str(width),
        "height": str(height),
    }

    if latitude is not None and longitude is not None:
        params["latitude"] = str(latitude)
        params["longitude"] = str(longitude)
    if postal is not None:
        params["postal"] = postal

    if polygons:
        polygon_strs = []
        for poly in polygons:
            coords = "[" + ",".join([f"[{p[0]},{p[1]}]" for p in poly]) + "]"
            if polygon_color:
                coords += f":{polygon_color}"
            polygon_strs.append(coords)
        params["polygons"] = "|".join(polygon_strs)

    if lines:
        line_strs = []
        for line in lines:
            coords = "[" + ",".join([f"[{p[0]},{p[1]}]" for p in line]) + "]"
            parts = [coords]
            if line_color:
                parts.append(line_color)
            if line_thickness is not None:
                parts.append(str(line_thickness))
            line_strs.append(":".join(parts))
        params["lines"] = "|".join(line_strs)

    if points:
        point_strs = []
        for pt in points:
            if points_color:
                s = f"[{pt[0]},{pt[1]},\"{points_color[0]},{points_color[1]},{points_color[2]}\"]"
            else:
                s = f"[{pt[0]},{pt[1]}]"
            point_strs.append(s)
        params["points"] = "|".join(point_strs)

    if color:
        params["color"] = color
    if fillColor:
        params["fillColor"] = fillColor

    query = "&".join(f"{k}={v}" for k, v in params.items())
    conn = http.client.HTTPSConnection("www.onemap.gov.sg", timeout=60)
    conn.request("GET", f"/api/staticmap/getStaticImage?{query}")
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    if resp.status != 200:
        raise RuntimeError(f"Static map request failed with status {resp.status}: {data[:200]}")
    return data