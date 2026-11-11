import json
import mimetypes
from contextlib import asynccontextmanager

import httpx
import uvicorn
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

# Same canonical config object as the backend (config/config.yaml). The proxy
# follows the backend's configured host/port; env vars are not consulted.
from config.get_config import config_data

# ============================================================================
# front.py 配置：直接修改下面这几个常量即可（不读取任何环境变量）。
# ============================================================================
# 后端地址。留空则按 config/config.yaml 的 server_host / server_port 推导
# （"0.0.0.0"/"::"/空 host 会按 127.0.0.1 处理，因为那是监听地址而非可连接目标）。
# 需要指向另一台机器/端口时才填写，例如 "http://10.0.0.5:8008"。
BACKEND_URL = ""
FRONT_HOST = "0.0.0.0"     # 反代监听地址
FRONT_PORT = 8010          # 反代监听端口
PROXY_TIMEOUT = 600.0      # 反代到后端的超时秒数（含 SSE 流；长任务可调大）
# ============================================================================

_bind_host = config_data.get("server_host", "127.0.0.1")
# "0.0.0.0"/"::" are listen addresses for the backend, not connectable
# destinations. Dialing them works on Windows by luck but is refused on other
# platforms, so the proxy always connects to the loopback address instead.
_host = "127.0.0.1" if _bind_host in ("0.0.0.0", "::", "") else _bind_host
_port = config_data["server_port"]
if not BACKEND_URL:
    BACKEND_URL = f"http://{_host}:{_port}"
DIST_DIR = Path(__file__).parent / "vue-front" / "dist"
DIST_ROOT = DIST_DIR.resolve()


def _safe_dist_file(rel: str):
    try:
        candidate = (DIST_DIR / rel).resolve()
        candidate.relative_to(DIST_ROOT)
    except (ValueError, OSError):
        return None
    return candidate if candidate.is_file() else None

client = httpx.AsyncClient(base_url=BACKEND_URL, timeout=PROXY_TIMEOUT)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await client.aclose()


app = FastAPI(title="front.py - Lightweight Frontend Proxy", lifespan=lifespan)

PROXY_PATHS = ("/api", "/upload-csv", "/upload-txt", "/tmp_imgs")
# All backend SSE (text/event-stream) routes end in "/stream/" (for example
# "/api/think/stream/" and "/api/generate-document/stream/unified/"), so they
# are detected structurally instead of via a hardcoded allowlist that has to be
# kept in sync with the routers. Only the few streaming routes that do NOT end
# in "/stream/" are listed here as exceptions.
_EXTRA_STREAM_PATHS = (
    "/api/generate-document/generate-yaml-outline/",
    "/api/generate-document/finalize/",
)
STATIC_EXTS = {".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg",
               ".ico", ".webp", ".woff", ".woff2", ".ttf", ".eot", ".json", ".map"}

# Extensions whose MIME type must not depend on the host: on CPython <= 3.12 the
# mimetypes module merges the Windows registry, which registers .js as text/plain
# on some machines. Browsers refuse ES modules served with a non-JS MIME type and
# show a blank page, so the types the built SPA relies on are pinned here.
_MIME_OVERRIDES = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".map": "application/json",
    ".svg": "image/svg+xml",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".eot": "application/vnd.ms-fontobject",
}


def _guess_mime(path: str):
    overridden = _MIME_OVERRIDES.get(Path(path).suffix.lower())
    if overridden:
        return overridden
    content_type, _ = mimetypes.guess_type(str(path))
    return content_type


# Hop-by-hop and body-framing headers must not be copied from the backend
# response: httpx already decodes the body, so forwarding the backend's original
# content-encoding/content-length would corrupt the proxied response.
_HOP_BY_HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
    "content-encoding", "content-length",
}


def _is_api_path(path: str) -> bool:
    return any(path.startswith(p) for p in PROXY_PATHS)


def _is_streaming_path(path: str) -> bool:
    return "/stream/" in path or path.startswith(_EXTRA_STREAM_PATHS)


def _build_target(path: str, request: Request) -> str:
    query = request.url.query
    return f"{path}?{query}" if query else path


def _forward_headers(request: Request) -> dict:
    headers = {}
    for key, value in request.headers.items():
        if key.lower() in ("host", "content-length", "content-encoding", "transfer-encoding", "connection"):
            continue
        headers[key] = value
    return headers


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def handler(full_path: str, request: Request):
    path = "/" + full_path

    if _is_api_path(path):
        if _is_streaming_path(path):
            return await proxy_stream(path, request)
        return await proxy_request(path, request)

    resolved = _safe_dist_file(full_path)
    if resolved is not None:
        return FileResponse(str(resolved), media_type=_guess_mime(str(resolved)) or "application/octet-stream")

    if full_path == "" or path == "/":
        index = DIST_DIR / "index.html"
        if index.is_file():
            return FileResponse(str(index), media_type="text/html")

    ext = Path(full_path).suffix
    if ext in STATIC_EXTS or (ext and len(ext) <= 5):
        resolved = _safe_dist_file(full_path)
        if resolved is not None:
            return FileResponse(str(resolved), media_type=_guess_mime(str(resolved)) or "application/octet-stream")
        return Response(status_code=404)

    index = DIST_DIR / "index.html"
    if index.is_file():
        return FileResponse(str(index), media_type="text/html")
    return Response(status_code=404)


async def proxy_request(path: str, request: Request) -> Response:
    target = _build_target(path, request)
    body = await request.body()
    headers = _forward_headers(request)

    try:
        resp = await client.request(
            method=request.method,
            url=target,
            headers=headers,
            content=body,
        )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers={k: v for k, v in resp.headers.items()
                     if k.lower() not in _HOP_BY_HOP_HEADERS},
        )
    except httpx.ConnectError:
        return Response(
            content=f'{{"error":"Cannot connect to backend at {BACKEND_URL}{path}"}}',
            status_code=502,
            media_type="application/json",
        )
    except Exception as e:
        return Response(
            content=f'{{"error":"Proxy error: {str(e)}"}}',
            status_code=500,
            media_type="application/json",
        )


async def proxy_stream(path: str, request: Request) -> Response:
    target = _build_target(path, request)
    body = await request.body()
    headers = _forward_headers(request)

    # Open the upstream stream before building the response so the backend's real
    # status code and headers are propagated. Opening it lazily (inside the
    # generator, as before) flattened every 4xx/5xx from a streaming route to
    # 200 + text/event-stream, so the frontend (which checks response.ok) treated
    # an error body as a live SSE stream and silently emitted nothing.
    stream = client.stream(
        method=request.method,
        url=target,
        headers=headers,
        content=body,
    )
    try:
        resp = await stream.__aenter__()
    except httpx.ConnectError:
        return Response(
            content=f'{{"error":"Cannot connect to backend at {BACKEND_URL}{path}"}}',
            status_code=502,
            media_type="application/json",
        )
    except Exception as e:
        return Response(
            content=f'{{"error":"Proxy error: {str(e)}"}}',
            status_code=500,
            media_type="application/json",
        )

    async def generate():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        except Exception as e:
            error = json.dumps(
                {"type": "error", "content": f"Proxy stream error: {e}"},
                ensure_ascii=False,
            )
            yield f"data: {error}\n\n".encode()
        finally:
            await stream.__aexit__(None, None, None)

    # content-type is supplied through media_type; hop-by-hop and body-framing
    # headers are dropped (httpx has already decoded the body).
    out_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in _HOP_BY_HOP_HEADERS and k.lower() != "content-type"
    }
    out_headers.setdefault("Cache-Control", "no-cache")
    out_headers.setdefault("X-Accel-Buffering", "no")

    return StreamingResponse(
        generate(),
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "text/event-stream"),
        headers=out_headers,
    )


if __name__ == "__main__":
    print(f"[front.py] Serving frontend from {DIST_DIR}")
    print(f"[front.py] Proxying API requests to {BACKEND_URL}")
    print(f"[front.py] Listening on http://{FRONT_HOST}:{FRONT_PORT}")
    uvicorn.run(app, host=FRONT_HOST, port=FRONT_PORT)