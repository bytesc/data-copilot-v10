from typing import List, Tuple, Optional, Dict, Union


# def get_minimap_func(lat_lng_list: Optional[List[Tuple[float, float]]] = None,
#                 postcode_list: Optional[List[str]] = None) -> str:
#     # lat_lng_list = [
#     #     (1.2996492424497, 103.8447478575),
#     #     (1.29963489170907, 103.845842317726),
#     #     # 可以继续添加更多经纬度
#     # ]
#
#     # postcode_list = ["123456",]
#     print(lat_lng_list,postcode_list)
#
#     # 基础字符串模板
#     base_string = '<iframe src="https://www.onemap.gov.sg/amm/amm.html?mapStyle=Default&zoomLevel=15'
#
#     # 遍历经纬度列表，添加标记
#     if lat_lng_list:
#         for lat, lng in lat_lng_list:
#             base_string += f'&marker=latLng:{lat},{lng}!colour:red'
#
#     if postcode_list:
#         for postalcode in postcode_list:
#             base_string += f'&marker=postalcode:{postalcode}!colour:red'
#
#     # 添加iframe的其他属性
#     base_string += '" height="480" width="480" scrolling="no" frameborder="0" allowfullscreen="allowfullscreen"></iframe>'
#
#     # print(base_string)
#     return base_string


MAX_MARKERS_PER_MAP = 50
MAX_URL_LENGTH = 3100

BASE_URL = 'https://www.onemap.gov.sg/amm/amm.html?mapStyle=Default&zoomLevel=15'

VALID_ICONS = {'fa-user', 'fa-mortar-board', 'fa-subway', 'fa-bus'}
VALID_COLORS = {'red', 'blue', 'green', 'black'}
VALID_ROUTE_TYPES = {'TRANSIT', 'WALK', 'DRIVE'}


def get_minimap_func(
        markers: Optional[List[Dict[str, Union[str, Tuple[float, float]]]]] = None,
) -> List[Tuple[str, str]]:
    """Generate OneMap AMM minimap URLs.

    OneMap AMM rejects URLs longer than ~3300 chars (HTTP 403). To stay below
    the limit, markers are split into multiple maps, each with at most
    MAX_MARKERS_PER_MAP markers and a URL no longer than MAX_URL_LENGTH.

    Returns a list of (url, iframe) tuples, one per map chunk.
    """
    if not markers:
        iframe = (f'<iframe src="{BASE_URL}" height="480" width="480" scrolling="no" '
                  f'frameborder="0" allowfullscreen="allowfullscreen"></iframe>')
        return [(BASE_URL, iframe)]

    chunks = []
    current = []
    for marker in markers:
        if 'location' not in marker:
            continue

        location = marker['location']
        if isinstance(location, tuple):
            loc_str = f'latLng:{location[0]},{location[1]}'
        else:
            loc_str = f'postalcode:{location}'

        marker_str = f'&marker={loc_str}'

        if 'icon' in marker:
            icon = marker['icon'] if marker['icon'] in VALID_ICONS else 'fa-user'
            marker_str += f'!icon:{icon}'

        if 'color' in marker:
            color = marker['color'] if marker['color'] in VALID_COLORS else 'red'
            marker_str += f'!colour:{color}'

        if 'route_type' in marker and 'route_dest' in marker:
            route_type = marker['route_type'] if marker['route_type'] in VALID_ROUTE_TYPES else 'WALK'

            dest = marker['route_dest']
            if isinstance(dest, tuple):
                dest_str = f'{dest[0]},{dest[1]}'
            else:
                dest_str = dest

            marker_str += f'!rType:{route_type}!rDest:{dest_str}'

        if (len(current) >= MAX_MARKERS_PER_MAP
                or len(BASE_URL + ''.join(current) + marker_str) > MAX_URL_LENGTH):
            if current:
                chunks.append(current)
            current = []
        current.append(marker_str)

    if current:
        chunks.append(current)

    maps = []
    for chunk in chunks:
        url = BASE_URL + ''.join(chunk)
        iframe = (f'<iframe src="{url}" height="480" width="480" scrolling="no" '
                  f'frameborder="0" allowfullscreen="allowfullscreen"></iframe>')
        maps.append((url, iframe))

    return maps

