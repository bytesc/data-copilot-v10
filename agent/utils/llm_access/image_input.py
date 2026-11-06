"""Build OpenAI-compatible user content with images for multimodal models.

Blackboard images are stored either as local file names (``tmp_imgs/xxx.png``)
or as full URLs. Local files and URLs pointing to the local ``tmp_imgs``
directory are encoded as base64 data URLs so the model provider can read them
even when it cannot reach this server.
"""

import base64
import mimetypes
import os
from functools import lru_cache
from urllib.parse import urlparse

LOCAL_IMAGE_DIR = "tmp_imgs"
MAX_IMAGE_BYTES = 20 * 1024 * 1024


@lru_cache(maxsize=256)
def _encode_local_image(path, mtime_ns, size):
    try:
        with open(path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode("ascii")
    except OSError:
        return None
    mime_type = mimetypes.guess_type(path)[0] or "image/png"
    return f"data:{mime_type};base64,{encoded}"


def _local_image_data_url(filename):
    if not filename:
        return None
    path = os.path.join(LOCAL_IMAGE_DIR, filename)
    try:
        stat = os.stat(path)
    except OSError:
        return None
    if not os.path.isfile(path) or stat.st_size > MAX_IMAGE_BYTES:
        return None
    mime_type = mimetypes.guess_type(path)[0]
    if not mime_type or not mime_type.startswith("image/"):
        return None
    return _encode_local_image(path, stat.st_mtime_ns, stat.st_size)


def _resolve_image_url(value):
    text = str(value or "").strip()
    if not text:
        return None
    # A usable image reference is a single clean token. HTML fragments and
    # multi-line strings (e.g. an accidentally captured iframe) must not be sent
    # as an image_url, otherwise the model gateway rejects the whole request.
    if any(ch.isspace() for ch in text) or "<" in text or ">" in text:
        return None
    if text.startswith("data:image/"):
        return text

    parsed = urlparse(text)
    if parsed.scheme in ("http", "https"):
        if "/tmp_imgs/" in parsed.path.replace("\\", "/"):
            return _local_image_data_url(os.path.basename(parsed.path))
        return text

    if text.startswith("file://"):
        text = urlparse(text).path

    filename = os.path.basename(text.replace("\\", "/"))
    return _local_image_data_url(filename)


def _image_label(value, index):
    text = str(value or "").strip()
    if not text or text.startswith("data:image/"):
        return f"image_{index}"
    parsed = urlparse(text)
    if parsed.scheme in ("http", "https"):
        return os.path.basename(parsed.path) or text
    return os.path.basename(text.replace("\\", "/")) or text


def build_user_content(text, images=None):
    """Return a plain string when there are no usable images, else content parts."""
    parts = [{"type": "text", "text": text or ""}]
    seen = set()
    for index, image in enumerate(images or [], 1):
        url = _resolve_image_url(image)
        if not url or url in seen:
            continue
        seen.add(url)
        parts.append({
            "type": "text",
            "text": f"Image filename: {_image_label(image, index)}",
        })
        parts.append({"type": "image_url", "image_url": {"url": url}})
    if len(parts) == 1:
        return text
    return parts
