import json
from typing import List, Tuple, Optional, Dict, Union

import pandas as pd
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt

from .copilot.utils.mpl_chinese_font import setup_chinese_font
setup_chinese_font()

from agent.utils.llm_access.LLM import get_llm
from .copilot.examples.path_tools import generate_img_path

from .map.get_onemap_minimap import get_onemap_minimap_func
from .map.get_onemap_staticmap import get_onemap_static_map_func
from .map.get_osm_minimap import get_osm_minimap_func
from .map.get_osm_staticmap import get_osm_static_map_func
from .map.get_streetdirectory_minimap import get_streetdirectory_minimap_func
from .llm_analysis.llm_predict_hdb import llm_predict_hdb_func, get_llm_predict_hdb_info
from .tools_def import engine, STATIC_URL

llm = get_llm()



# def get_onemap_minimap(lat_lng_list: Optional[List[Tuple[float, float]]] = None,
#                 postcode_list: Optional[List[str]] = None) -> str:
#     """
#     get_onemap_minimap(lat_lng_list: Optional[List[Tuple[float, float]]] = None, postcode_list: Optional[List[str]] = None) -> str:
#     Generate an HTML iframe for a minimap with optional markers in latitude and longitude pairs or or postal codes.
#     Returns an HTML iframe string.
#
#     The function creates an HTML iframe that embeds a minimap from OneMap.sg.
#     Users can specify a list of latitude and longitude pairs or postal codes
#     to be marked on the map.
#
#     Args:
#     - lat_lng_list (Optional[List[Tuple[float, float]]]): A list of tuples,
#       where each tuple contains a latitude and longitude pair for a marker.
#       Default is None.
#     - postcode_list (Optional[List[str]]): A list of postal codes to be marked
#       on the map. Default is None.
#
#     Returns:
#     - str: An HTML iframe string that can be embedded in a webpage to display
#       the minimap with the specified markers.
#
#     Example usage:
#     ```python
#     get_onemap_minimap_func(lat_lng_list=[(1.2996492424497, 103.8447478575), (1.29963489170907, 103.845842317726)])
#     get_onemap_minimap_func(postcode_list=["123456"])
#     ```
#
#     """
#     html = get_onemap_minimap_func(lat_lng_list, postcode_list)
#     return html


def get_onemap_minimap(
        markers: Optional[List[Dict[str, Union[str, Tuple[float, float]]]]] = None
) -> str:
    """
    get_onemap_minimap(markers: Optional[List[Dict[str, Union[str, Tuple[float, float]]]]] = None) -> str:
    Generate an HTML iframe for a minimap with customizable markers and routes from OneMap.sg.
    Returns a markdown link followed by the HTML iframe string.

    The function creates an HTML iframe that embeds a minimap from OneMap.sg with
    customizable markers and optional routes between them. Destination points for
    routes must also be added as markers on the map!!!

    Args:
    - markers: List of marker dictionaries. Each marker can have:
        * 'location': Either a postalcode (str) or latLng tuple (float, float) (REQUIRED)
        * 'color': color from: 'red', 'blue', 'green', 'black' (REQUIRED)
        * 'icon': Optional icon name from: 'fa-user', 'fa-mortar-board', 'fa-subway', 'fa-bus', 'fa-star'
        * 'route_type': Optional route type from: 'TRANSIT', 'WALK', 'DRIVE'
        * 'route_dest': Optional destination for route as latLng tuple (float, float). Destination point must be added as another individual marker point in the list!!!

    Returns:
    - str: A markdown link "[🔗 Open Map on OneMap.sg](url)" followed by a blank line and the HTML iframe.

    Example usage(just example, do not use the data):
    ```python
    get_onemap_minimap([{'location': (1.29203, 103.843), 'color': 'red'}])
    dest = (1.33587, 103.854)
    get_onemap_minimap([{'location': "238889", 'color': 'black', 'icon': 'fa-bus', 'route_type': 'WALK', 'route_dest': dest}])
    ```

    """
    maps = get_onemap_minimap_func(markers)
    parts = []
    for i, (url, iframe) in enumerate(maps, start=1):
        label = f" (Part {i})" if len(maps) > 1 else ""
        parts.append(f"[🔗 Open Map on OneMap.sg{label}]({url})\n\n{iframe}")
    output = "\n\n".join(parts)
    return output


def get_osm_minimap(
        markers: Optional[List[Dict[str, Union[str, Tuple[float, float]]]]] = None,
        zoom: int = 15,
        width: int = 480,
        height: int = 480,
) -> str:
    """
    get_osm_minimap(markers=None, zoom=15, width=480, height=480) -> str:
    Generate an HTML iframe for a minimap with customizable markers from OpenStreetMap.
    Returns a markdown link followed by the HTML iframe string.

    Unlike OneMap.sg, OpenStreetMap covers the whole world and needs no API key.
    Markers are rendered on OpenStreetMap tiles inside the iframe, and a shareable
    OpenStreetMap link covering the markers' bounding box is also returned.
    When there are too many markers, they are split into multiple maps (Part 1, 2, ...).

    Args:
    - markers: List of marker dictionaries. Each marker can have:
        * 'location': A latLng tuple (float, float) (REQUIRED). Postal codes are
          NOT supported for OpenStreetMap.
        * 'color': Optional color from: 'red', 'blue', 'green', 'black',
          'yellow', 'orange', 'purple', 'white', 'grey'. Default 'red'.
        * 'icon': Optional Font Awesome 4 icon name, e.g. 'fa-user', 'fa-mortar-board',
          'fa-subway', 'fa-bus', 'fa-music', 'fa-star'. Default 'fa-map-marker'.
        * 'label': Optional tooltip text shown on hover.
        * 'popup': Optional HTML popup content shown on click.
    - zoom (int): Initial zoom level used when there is a single marker. Default 15.
      When there are multiple markers the map auto-fits their bounding box.
    - width (int): iframe width in pixels. Default 480.
    - height (int): iframe height in pixels. Default 480.

    Returns:
    - str: A markdown link "[🔗 Open Map on OpenStreetMap](url)" followed by a blank
      line and the HTML iframe.

    Example usage(just example, do not use the data):
    ```python
    get_osm_minimap([{'location': (1.29203, 103.843), 'color': 'red'}])
    get_osm_minimap([
        {'location': (1.32085, 103.808), 'color': 'red', 'icon': 'fa-mortar-board', 'label': 'NUS'},
        {'location': (1.36886, 103.834), 'color': 'black'},
    ], zoom=15)
    ```
    """
    maps = get_osm_minimap_func(markers, zoom=zoom, width=width, height=height)
    parts = []
    for i, (url, iframe) in enumerate(maps, start=1):
        label = f" (Part {i})" if len(maps) > 1 else ""
        parts.append(f"[🔗 Open Map on OpenStreetMap{label}]({url})\n\n{iframe}")
    output = "\n\n".join(parts)
    return output


def get_streetdirectory_minimap(
        markers: Optional[List[Dict[str, Union[str, Tuple[float, float]]]]] = None,
        width: int = 480,
        height: int = 480,
) -> str:
    """
    get_streetdirectory_minimap(markers=None, width=480, height=480) -> str:
    Generate an HTML iframe for a minimap with locations from StreetDirectory.com.
    Returns a markdown link followed by the HTML iframe string.

    StreetDirectory.com is a Singapore-focused map service. Unlike OpenStreetMap
    it has no public tile API, so locations are resolved through StreetDirectory's
    search API and each resolved location is embedded as an iframe of its official
    location page. Locations that cannot be resolved are skipped.

    Args:
    - markers: List of marker dictionaries. Each marker can have:
        * 'location': A Singapore postal code (str) or an address/building name
          (str) (REQUIRED). A latLng tuple (float, float) is also accepted but
          StreetDirectory's search API usually cannot reverse geocode raw
          coordinates, so prefer postal codes or address strings. For latLng
          markers use get_osm_minimap instead.
    - width (int): iframe width in pixels. Default 480.
    - height (int): iframe height in pixels. Default 480.

    Returns:
    - str: A markdown link "[🔗 Open Map on StreetDirectory.com](url)" followed by
      a blank line and the HTML iframe.

    Example usage(just example, do not use the data):
    ```python
    get_streetdirectory_minimap([{'location': "238889"}])
    get_streetdirectory_minimap([
        {'location': "238889"},
        {'location': "1 Raffles Place"},
    ])
    ```
    """
    maps = get_streetdirectory_minimap_func(markers, width=width, height=height)
    parts = []
    for i, (url, iframe) in enumerate(maps, start=1):
        label = f" (Part {i})" if len(maps) > 1 else ""
        parts.append(f"[🔗 Open Map on StreetDirectory.com{label}]({url})\n\n{iframe}")
    output = "\n\n".join(parts)
    return output


def get_osm_static_map(
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
    points_color: Optional[Tuple[int, int, int]] = None,
    color: Optional[str] = None,
    fillColor: Optional[str] = None,
) -> str:
    """
    get_osm_static_map(latitude, longitude, zoom=15, width=512, height=512, markers=None, polygons=None, polygon_color=None, lines=None, line_color=None, line_thickness=None, points=None, points_color=None, color=None, fillColor=None) -> str:
    Generate a static map PNG image from OpenStreetMap tiles and save it locally. Returns the image URL path.

    Downloads OpenStreetMap tiles around the given center, stitches them into a
    single PNG, and optionally draws markers, polygons, lines, and points overlays
    on top. Unlike OneMap.sg, OpenStreetMap covers the whole world and needs no API key.
    The returned image includes "© OpenStreetMap contributors" attribution.

    Args:
    - latitude (float, required): Latitude of the map center in WGS84 format.
    - longitude (float, required): Longitude of the map center in WGS84 format.
    - zoom (int): Zoom level 0-19. Default 15.
    - width (int): Image width in pixels, max 2048. Default 512.
    - height (int): Image height in pixels, max 2048. Default 512.
    - markers (List[Dict], optional): List of marker dicts, each with:
        * 'location': A latLng tuple (float, float) (REQUIRED). Postal codes are
          NOT supported for OpenStreetMap.
        * 'color': Optional color from: 'red', 'blue', 'green', 'black',
          'yellow', 'orange', 'purple', 'white', 'grey'. Default 'red'.
    - polygons (List[List[Tuple[float,float]]], optional): List of polygons, each a list of (lat, lng) tuples.
    - polygon_color (str, optional): RGB color for polygon outlines, e.g. "255,0,0" or "#ff0000".
    - lines (List[List[Tuple[float,float]]], optional): List of lines, each a list of (lat, lng) tuples.
    - line_color (str, optional): RGB color for lines, e.g. "177,0,0".
    - line_thickness (int, optional): Thickness of lines in pixels. Default 3.
    - points (List[Tuple[float,float]], optional): List of (lat, lng) point coordinates.
    - points_color (Tuple[int,int,int], optional): RGB tuple for points color, e.g. (255,255,178).
    - color (str, optional): RGB color for ALL lines, e.g. "255,0,255".
    - fillColor (str, optional): RGB fill color for ALL polygons, e.g. "0,255,0".

    Returns:
    - str: URL path to the saved static map PNG image.

    Example usage:
    ```python
    path = get_osm_static_map(latitude=1.31955, longitude=103.84223, zoom=17)
    yield path
    ```
    """
    img_bytes = get_osm_static_map_func(
        latitude=latitude,
        longitude=longitude,
        zoom=zoom,
        width=width,
        height=height,
        markers=markers,
        polygons=polygons,
        polygon_color=polygon_color,
        lines=lines,
        line_color=line_color,
        line_thickness=line_thickness,
        points=points,
        points_color=points_color,
        color=color,
        fillColor=fillColor,
    )
    path = generate_img_path()
    with open(path, "wb") as f:
        f.write(img_bytes)
    return STATIC_URL + path[2:]


def get_onemap_static_map(
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
) -> str:
    """
    get_onemap_static_map(layerchosen="default", latitude=None, longitude=None, postal=None, zoom=15, width=512, height=512, polygons=None, polygon_color=None, lines=None, line_color=None, line_thickness=None, points=None, points_color=None, color=None, fillColor=None) -> str:
    Generate a static map image from OneMap.sg PNG API and save it locally. Returns the image URL path.
    The maximum resolution is 512 x 512 pixels.

    Creates a static map with optional polygons, lines, and points overlay, saves it as a PNG file, and returns the URL path to access the image.

    Args:
    - layerchosen (str): Base map style: 'night', 'grey', 'original', 'default', 'landlot'. Default 'default'.
    - latitude (float, optional): Latitude in WGS84 format. Use with longitude.
    - longitude (float, optional): Longitude in WGS84 format. Use with latitude.
    - postal (str, optional): Singapore postal code. Alternative to latitude/longitude.
    - zoom (int): Zoom level 11-19. Default 15.
    - width (int): Image width 128-512. Default 512.
    - height (int): Image height 128-512. Default 512.
    - polygons (List[List[Tuple[float, float]]], optional): List of polygons, each is a list of (lat, lng) tuples.
    - polygon_color (str, optional): RGB color for polygons, e.g. "255,0,0".
    - lines (List[List[Tuple[float, float]]], optional): List of lines, each is a list of (lat, lng) tuples.
    - line_color (str, optional): RGB color for lines, e.g. "177,0,0".
    - line_thickness (int, optional): Thickness of lines.
    - points (List[Tuple[float, float]], optional): List of (lat, lng) point coordinates.
    - points_color (Tuple[int,int,int], optional): RGB tuple for points color, e.g. (255,255,178).
    - color (str, optional): RGB color for ALL lines, e.g. "255,0,255".
    - fillColor (str, optional): RGB fill color for ALL polygons, e.g. "0,255,0".

    Returns:
    - str: URL path to the saved static map PNG image.

    Example usage:
    ```python
    path = get_onemap_static_map(latitude=1.31955, longitude=103.84223, zoom=17)
    yield path
    ```
    """
    img_bytes = get_onemap_static_map_func(
        layerchosen=layerchosen,
        latitude=latitude,
        longitude=longitude,
        postal=postal,
        zoom=zoom,
        width=width,
        height=height,
        polygons=polygons,
        polygon_color=polygon_color,
        lines=lines,
        line_color=line_color,
        line_thickness=line_thickness,
        points=points,
        points_color=points_color,
        color=color,
        fillColor=fillColor,
    )
    path = generate_img_path()
    with open(path, "wb") as f:
        f.write(img_bytes)
    return STATIC_URL + path[2:]





def predict_hdb_price(from_date: str = None, to_date: str = None, plan_area=None, blk_no=None, street=None,
                      flat_model=None, flat_type=None, storey_range=None,
                      floor_area_sqm_from=None, floor_area_sqm_to=None,
                      lease_commence_date_from=None, lease_commence_date_to=None) -> tuple[pd.DataFrame, str]:
    """
def predict_hdb_price(from_date: str = None, to_date: str = None, plan_area=None, blk_no=None, street=None,flat_model=None, flat_type=None, storey_range=None,floor_area_sqm_from=None, floor_area_sqm_to=None,lease_commence_date_from=None, lease_commence_date_to=None) -> tuple[pd.DataFrame, str]:
Predict HDB resale prices using history data based on various property features. The function is used to predict a kind of hdb with certain features, it works well even only some of the parameters provided!!!
The function returns both predicted prices dataFrame and a path of image of historical vs predicted prices.

Args:
- from_date (str, optional): Start date for prediction in "YYYY-MM" format.
- to_date (str, optional): End date for prediction in "YYYY-MM" format.
- plan_area (str, optional): Planning area where the flat is located (e.g., "ANG MO KIO").
- blk_no (str, optional): Block number of the HDB flat.
- street (str, optional): Street name where the flat is located (e.g., "ANG MO KIO AVENUE 1").
- flat_model (str, optional): Model of flat (e.g., "IMPROVED", "NEW GENERATION").
- flat_type (str, optional): Type of flat (e.g., "1 ROOM", "3 ROOM").
- storey_range (str, optional): Storey range (e.g., "04 TO 06", "10 TO 12").
- floor_area_sqm_from (float, optional): Minimum floor area in square meters for filtering.
- floor_area_sqm_to (float, optional): Maximum floor area in square meters for filtering.
- lease_commence_date_from (int, optional): Minimum lease commence year for filtering.
- lease_commence_date_to (int, optional): Maximum lease commence year for filtering.

Returns:
- pd.DataFrame: A DataFrame containing predicted prices with columns:
    * 'month': Prediction month in "YYYY-MM" format
    * 'predicted_price': Predicted resale price in SGD
- str: File path to the generated visualization image showing historical and predicted prices

Example usage:
```python
price_df, img_path = predict_hdb_price(
    from_date="2025-01",
    to_date="2025-12",
    plan_area="ANG MO KIO",
    flat_type="3 ROOM",
    flat_model="NEW GENERATION",
    street="ANG MO KIO AVENUE 1",
    storey_range="04 TO 06",
)
yield price_df
yield img_path
```
    """
    predict_df = llm_predict_hdb_func(engine=engine, llm=llm, from_date=from_date, to_date=to_date,
                                      plan_area=plan_area, blk_no=blk_no, street=street,
                                      flat_model=flat_model, flat_type=flat_type, storey_range=storey_range,
                                      floor_area_sqm_from=floor_area_sqm_from, floor_area_sqm_to=floor_area_sqm_to,
                                      lease_commence_date_from=lease_commence_date_from,
                                      lease_commence_date_to=lease_commence_date_to)
    search_conditions, hdb_price_history, sample = get_llm_predict_hdb_info(engine,
                                                                            plan_area=plan_area, blk_no=blk_no,
                                                                            street=street,
                                                                            flat_model=flat_model, flat_type=flat_type,
                                                                            storey_range=storey_range,
                                                                            floor_area_sqm_from=floor_area_sqm_from,
                                                                            floor_area_sqm_to=floor_area_sqm_to,
                                                                            lease_commence_date_from=lease_commence_date_from,
                                                                            lease_commence_date_to=lease_commence_date_to)
    path = generate_img_path()

    import matplotlib.pyplot as plt
    import pandas as pd
    from matplotlib.dates import AutoDateLocator, ConciseDateFormatter

    history_df = pd.DataFrame(hdb_price_history)
    history_df['month'] = pd.to_datetime(history_df['month'])
    predict_df['month'] = pd.to_datetime(predict_df['month'])

    plt.figure(figsize=(12, 6))
    ax = plt.gca()

    if 'avg_resale_price' in history_df.columns:
        plt.scatter(history_df['month'], history_df['avg_resale_price'],
                    label='Historical Data Points', color='blue', alpha=0.6)
        y_values = history_df['avg_resale_price']
    elif 'resale_price' in history_df.columns:
        plt.scatter(history_df['month'], history_df['resale_price'],
                    label='Historical Data Points', color='blue', alpha=0.6)
        y_values = history_df['resale_price']

    if len(history_df) > 1:
        history_df = history_df.sort_values('month')
        window_size = max(2, min(6, len(history_df) // 3))
        smooth_df = history_df.copy()
        if 'avg_resale_price' in smooth_df.columns:
            smooth_df['smoothed'] = smooth_df['avg_resale_price'].rolling(window=window_size, center=True).mean()
        else:
            smooth_df['smoothed'] = smooth_df['resale_price'].rolling(window=window_size, center=True).mean()

        smooth_df['smoothed'] = smooth_df['smoothed'].interpolate()

        plt.plot(smooth_df['month'], smooth_df['smoothed'],
                 label='Historical Trend', color='green', linewidth=2)

        last_historical_date = smooth_df['month'].iloc[-1]
        last_historical_price = smooth_df['smoothed'].iloc[-1]

        first_predicted_date = predict_df['month'].iloc[0]
        first_predicted_price = predict_df['predicted_price'].iloc[0]

        plt.plot([last_historical_date, first_predicted_date],
                 [last_historical_price, first_predicted_price],
                 color='green', linestyle='--', alpha=0.5)

    plt.plot(predict_df['month'], predict_df['predicted_price'],
             label='Predicted Price', linestyle='-', color='red')

    locator = AutoDateLocator()
    formatter = ConciseDateFormatter(locator)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)

    plt.xlabel('Date')
    plt.ylabel('Price (SGD)')
    plt.title('HDB Resale Price History and Prediction')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(path)
    plt.close()

    return predict_df, STATIC_URL + path[2:]

