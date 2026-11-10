import os
import mimetypes
from contextlib import asynccontextmanager

import httpx
import uvicorn
import yaml
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

# Resolve the config relative to this file so the proxy can be started from any
# working directory (a CWD-relative path broke startup when launched elsewhere).
_CONFIG_PATH = Path(__file__).parent / "config" / "config.yaml"
with open(_CONFIG_PATH, encoding="utf-8") as f:
    _cfg = yaml.safe_load(f) or {}
_bind_host = _cfg.get("server_host", "127.0.0.1")
# "0.0.0.0"/"::" are listen addresses for the backend, not connectable
# destinations. Dialing them works on Windows by luck but is refused on other
# platforms, so the proxy always connects to the loopback address instead.
_host = "127.0.0.1" if _bind_host in ("0.0.0.0", "::", "") else _bind_host
_port = _cfg["server_port"]
BACKEND_URL = os.getenv("BACKEND_URL", f"http://{_host}:{_port}")
FRONT_HOST = os.getenv("FRONT_HOST", "0.0.0.0")
FRONT_PORT = int(os.getenv("FRONT_PORT", "8010"))
DIST_DIR = Path(__file__).parent / "vue-front" / "dist"
DIST_ROOT = DIST_DIR.resolve()


def _safe_dist_file(rel: str):
    try:
        candidate = (DIST_DIR / rel).resolve()
        candidate.relative_to(DIST_ROOT)
    except (ValueError, OSError):
        return None
    return candidate if candidate.is_file() else None

client = httpx.AsyncClient(base_url=BACKEND_URL, timeout=600.0)


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
        content_type, _ = mimetypes.guess_type(str(resolved))
        return FileResponse(str(resolved), media_type=content_type or "application/octet-stream")

    if full_path == "" or path == "/":
        index = DIST_DIR / "index.html"
        if index.is_file():
            return FileResponse(str(index), media_type="text/html")

    ext = Path(full_path).suffix
    if ext in STATIC_EXTS or (ext and len(ext) <= 5):
        resolved = _safe_dist_file(full_path)
        if resolved is not None:
            content_type, _ = mimetypes.guess_type(str(resolved))
            return FileResponse(str(resolved), media_type=content_type or "application/octet-stream")
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


async def proxy_stream(path: str, request: Request) -> StreamingResponse:
    target = _build_target(path, request)
    body = await request.body()
    headers = _forward_headers(request)

    async def generate():
        try:
            async with client.stream(
                method=request.method,
                url=target,
                headers=headers,
                content=body,
            ) as resp:
                async for chunk in resp.aiter_bytes():
                    yield chunk
        except httpx.ConnectError:
            yield f'{{"error":"Cannot connect to backend at {BACKEND_URL}{path}"}}'.encode()
        except Exception as e:
            yield f'{{"error":"Proxy stream error: {str(e)}"}}'.encode()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


if __name__ == "__main__":
    print(f"[front.py] Serving frontend from {DIST_DIR}")
    print(f"[front.py] Proxying API requests to {BACKEND_URL}")
    print(f"[front.py] Listening on http://{FRONT_HOST}:{FRONT_PORT}")
    uvicorn.run(app, host=FRONT_HOST, port=FRONT_PORT)