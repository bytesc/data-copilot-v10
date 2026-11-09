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
# Server-side guards (the frontend caps uploads too, but clients cannot be
# trusted): bound how many images a single request may decode/save and how many
# total bytes it may write to disk.
MAX_IMAGES_PER_REQUEST = 10
MAX_TOTAL_IMAGE_BYTES = 50 * 1024 * 1024


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
    """Decode base64 ``uploaded`` items, save them, and update history/blackboard.

    Enforces ``MAX_IMAGES_PER_REQUEST`` and ``MAX_TOTAL_IMAGE_BYTES`` across the
    whole request so a malicious client cannot flood ``tmp_imgs``. The base64
    string length is used as a conservative upper bound on decoded bytes. Items
    that are over budget are dropped from ``uploaded`` (replaced only by their
    already-saved file names) so no raw base64 payload is ever left in the
    history when the limits are exceeded.
    """
    if not isinstance(history, list):
        return history

    created: List[str] = []
    processed = 0
    dropped = 0
    total_raw_bytes = 0
    budget_exhausted = False

    for entry in history:
        if not isinstance(entry, dict) or entry.get("role") != "user":
            continue
        uploaded = entry.get("uploaded")
        if not isinstance(uploaded, list) or not uploaded:
            continue

        names: List[str] = []
        # Any non-string item is a staged base64 payload. The entry's ``uploaded``
        # list is always rebuilt so a raw base64 string can never survive into
        # the saved history / LLM context, even for entries that are skipped
        # because the per-request budget was already exhausted. Previously the
        # outer loop ``break``ed, leaving the remaining entries' base64 payloads
        # untouched (and re-persisted) once the limits were hit.
        changed = False
        for item in uploaded:
            if isinstance(item, str):
                if item:
                    names.append(item)
                continue
            changed = True
            if budget_exhausted or processed >= MAX_IMAGES_PER_REQUEST:
                budget_exhausted = True
                dropped += 1
                continue
            data = _item_data(item)
            if not data:
                dropped += 1
                continue
            # The base64 string length is used as a conservative upper bound on
            # the decoded byte size before spending budget on decoding.
            if total_raw_bytes + len(data) > MAX_TOTAL_IMAGE_BYTES:
                budget_exhausted = True
                dropped += 1
                continue
            processed += 1
            total_raw_bytes += len(data)
            filename = save_base64_image(data)
            if filename:
                names.append(filename)
                created.append(filename)
            else:
                dropped += 1

        if changed:
            entry["uploaded"] = names

    if budget_exhausted or dropped:
        print(
            "[image_ingest] WARNING: some uploaded images were dropped "
            f"(saved={processed}, dropped={dropped}, raw_bytes={total_raw_bytes}); "
            "raw base64 payloads were stripped from the history."
        )

    if created:
        history = _merge_selected_images(history, created)
    return history
