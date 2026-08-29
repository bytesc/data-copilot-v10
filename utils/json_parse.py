import json


def parse_json(raw: str) -> dict | None:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    for prefix in ('```json', '```'):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
    for suffix in ('```',):
        if raw.endswith(suffix):
            raw = raw[:-len(suffix)]
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None