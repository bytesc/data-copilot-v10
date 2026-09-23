import os
import asyncio
import mimetypes
from urllib.parse import urlparse
import httpx
import uvicorn
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response, HTMLResponse
from fastapi.staticfiles import StaticFiles

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8008")
FRONT_HOST = os.getenv("FRONT_HOST", "0.0.0.0")
FRONT_PORT = int(os.getenv("FRONT_PORT", "8010"))
DIST_DIR = Path(__file__).parent / "vue-front" / "dist"

app = FastAPI(title="front.py - Lightweight Frontend Proxy")
client = httpx.AsyncClient(base_url=BACKEND_URL, timeout=30.0)

PROXY_PATHS = ("/api", "/upload-csv", "/upload-txt", "/tmp_imgs")
STATIC_EXTS = {".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg",
               ".ico", ".webp", ".woff", ".woff2", ".ttf", ".eot", ".json", ".map"}


def _is_api_path(path: str) -> bool:
    return any(path.startswith(p) for p in PROXY_PATHS)


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def handler(full_path: str, request: Request):
    path = "/" + full_path

    if _is_api_path(path):
        return await proxy_request(path, request)

    filepath = DIST_DIR / full_path
    if filepath.is_file():
        content_type, _ = mimetypes.guess_type(str(filepath))
        return FileResponse(str(filepath), media_type=content_type or "application/octet-stream")

    if full_path == "" or path == "/":
        index = DIST_DIR / "index.html"
        if index.is_file():
            return FileResponse(str(index), media_type="text/html")

    ext = Path(full_path).suffix
    if ext in STATIC_EXTS or (ext and len(ext) <= 5):
        filepath = DIST_DIR / full_path
        if filepath.is_file():
            content_type, _ = mimetypes.guess_type(str(filepath))
            return FileResponse(str(filepath), media_type=content_type or "application/octet-stream")
        return Response(status_code=404)

    index = DIST_DIR / "index.html"
    if index.is_file():
        return FileResponse(str(index), media_type="text/html")
    return Response(status_code=404)


async def proxy_request(path: str, request: Request) -> Response:
    query = request.url.query
    target = f"{path}?{query}" if query else path

    body = await request.body()
    headers = {}
    for key, value in request.headers.items():
        if key.lower() in ("host", "content-length", "content-encoding", "transfer-encoding", "connection"):
            continue
        headers[key] = value

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
            headers=dict(resp.headers),
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


@app.on_event("shutdown")
async def shutdown():
    await client.aclose()


if __name__ == "__main__":
    print(f"[front.py] Serving frontend from {DIST_DIR}")
    print(f"[front.py] Proxying API requests to {BACKEND_URL}")
    print(f"[front.py] Listening on http://{FRONT_HOST}:{FRONT_PORT}")
    uvicorn.run(app, host=FRONT_HOST, port=FRONT_PORT)