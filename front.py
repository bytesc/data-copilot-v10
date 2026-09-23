import os
import mimetypes
import httpx
import uvicorn
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8008")
FRONT_HOST = os.getenv("FRONT_HOST", "0.0.0.0")
FRONT_PORT = int(os.getenv("FRONT_PORT", "8010"))
DIST_DIR = Path(__file__).parent / "vue-front" / "dist"

app = FastAPI(title="front.py - Lightweight Frontend Proxy")
client = httpx.AsyncClient(base_url=BACKEND_URL, timeout=600.0)

PROXY_PATHS = ("/api", "/upload-csv", "/upload-txt", "/tmp_imgs")
STREAM_PATHS = ("/api/generate-and-execute/stream/", "/api/plain-chat/stream/",
                "/api/filter-db-fields/stream/", "/api/filter-functions/stream/",
                "/api/think/stream/", "/api/act/stream/", "/api/observe/stream/",
                "/api/action/stream/", "/api/generate-document/stream/")
STATIC_EXTS = {".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg",
               ".ico", ".webp", ".woff", ".woff2", ".ttf", ".eot", ".json", ".map"}


def _is_api_path(path: str) -> bool:
    return any(path.startswith(p) for p in PROXY_PATHS)


def _is_streaming_path(path: str) -> bool:
    return any(path.startswith(p) for p in STREAM_PATHS)


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


@app.on_event("shutdown")
async def shutdown():
    await client.aclose()


if __name__ == "__main__":
    print(f"[front.py] Serving frontend from {DIST_DIR}")
    print(f"[front.py] Proxying API requests to {BACKEND_URL}")
    print(f"[front.py] Listening on http://{FRONT_HOST}:{FRONT_PORT}")
    uvicorn.run(app, host=FRONT_HOST, port=FRONT_PORT)