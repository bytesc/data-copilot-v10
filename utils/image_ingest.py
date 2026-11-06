"""Ingest user-uploaded images carried as base64 inside the JSON request.

The frontend stages images locally and, on send, attaches them to the user
history entry as ``uploaded`` items of the form ``{"name": ..., "data":
"data:image/png;base64,..."}``.  This module runs in the request envelope
middleware, decodes those payloads, saves them under ``tmp_imgs`` as
``upload_<8 random letters>.png`` (the same naming scheme as generated
images), rewrites the entry so ``uploaded`` becomes the saved file-name list,
and merges the file names into the blackboard ``selected_images`` region.

Processing is idempotent: entries whose ``uploaded`` items are already plain
file-name strings (persisted from a previous phase) are left untouched and are
not re-merged.
"""

import base64
import binascii
import io
import os
from typing import Any, List, Optional

from PIL import Image

from agent.tools.copilot.examples.path_tools import generate_upload_img_path
from utils.blackboard import SELECTED_IMAGES, get_blackboard, replace_blackboard

STATIC_FOLDER = "tmp_imgs"
MAX_IMAGE_BYTES = 20 * 1024 * 1024


def _decode_base64(data: str) -> Optional[bytes]:
    if not isinstance(data, str):
        return None
    text = data.strip()
    if not text:
        return None
    if ";base64," in text:
        text = text.split(";base64,", 1)[1]
    elif text.startswith("data:"):
        return None
    try:
        return base64.b64decode(text, validate=False)
    except (binascii.Error, ValueError):
        return None


def save_base64_image(data: str) -> Optional[str]:
    """Decode one base64 image and save it as ``upload_<8>.png``."""
    content = _decode_base64(data)
    if not content or len(content) > MAX_IMAGE_BYTES:
        return None
    try:
        image = Image.open(io.BytesIO(content))
        image.load()
    except Exception:
        return None

    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

    os.makedirs(STATIC_FOLDER, exist_ok=True)
    filename = ""
    for _ in range(20):
        candidate = os.path.basename(generate_upload_img_path())
        if not os.path.exists(os.path.join(STATIC_FOLDER, candidate)):
            filename = candidate
            break
    if not filename:
        image.close()
        return None

    try:
        image.save(os.path.join(STATIC_FOLDER, filename), format="PNG")
    except Exception:
        return None
    finally:
        image.close()
    return filename


def _item_data(item: Any) -> Optional[str]:
    if isinstance(item, dict):
        for key in ("data", "base64", "content", "image"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _merge_selected_images(history: List[dict], filenames: List[str]) -> List[dict]:
    board = get_blackboard(history)
    region = board.get(SELECTED_IMAGES)
    existing = region.get("images") if isinstance(region, dict) else None
    images = list(existing) if isinstance(existing, list) else []

    seen = set()
    for item in images:
        if isinstance(item, dict) and item.get("path"):
            seen.add(item["path"])
        elif isinstance(item, str):
            seen.add(item)

    for name in filenames:
        if name in seen:
            continue
        seen.add(name)
        images.append({"path": name, "reason": "user uploaded image"})

    board[SELECTED_IMAGES] = {"images": images}
    return replace_blackboard(history, board)


def ingest_uploaded_images(history: Any) -> Any:
    """Decode base64 ``uploaded`` items, save them, and update history/blackboard."""
    if not isinstance(history, list):
        return history

    created: List[str] = []
    for entry in history:
        if not isinstance(entry, dict) or entry.get("role") != "user":
            continue
        uploaded = entry.get("uploaded")
        if not isinstance(uploaded, list) or not uploaded:
            continue

        names: List[str] = []
        for item in uploaded:
            if isinstance(item, str):
                if item:
                    names.append(item)
                continue
            data = _item_data(item)
            if not data:
                continue
            filename = save_base64_image(data)
            if filename:
                names.append(filename)
                created.append(filename)

        if names:
            entry["uploaded"] = names

    if created:
        history = _merge_selected_images(history, created)
    return history
