import os
os.environ['MPLBACKEND'] = 'Agg'

import asyncio
import contextvars
import io
import json
import math
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
import pandas as pd
import sqlalchemy
import uvicorn
from fastapi import FastAPI, Request, Form
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi import File, UploadFile, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.responses import JSONResponse


from agent.plain_chat import get_plain_chat, get_plain_chat_stream
from agent.data_comment import get_llm_data_comment

from data_access.insert_data_from_csv import process_csv_to_database
from data_access.read_db import get_all_comments_from_table
from data_access.db_conn import engine
from utils.get_config import config_data
from utils.image_ingest import ingest_uploaded_images
from utils.column_ddl import build_column_comment_sql, build_table_comment_sql

from agent.agent import  generate_and_execute_stream, get_db
from utils.process_file import process_file_content
from agent.utils.llm_access.LLM import (
    list_model_configs,
    get_current_model_id,
    get_current_reasoning_effort,
    get_current_style,
    apply_request_selection,
)
from data_access.session_log import record_session_operation, create_session_log_table
from data_access.observe_log import (
    create_observe_log_tables, log_observe_cycle, log_observe_session,
    list_sessions, reconstruct_conversation_history
)
from utils.perf_log import perf_api, perf_context
from data_access.report_log import create_report_log_table, get_generated_files
_ENABLE_BASE_KNOWLEDGE = config_data.get('enable_base_knowledge', True)
_ENABLE_EDIT = config_data.get('enable_edit', True)

def _require_edit_enabled():
    if not _ENABLE_EDIT:
        raise HTTPException(status_code=403, detail="Editing is disabled by configuration")


def _quote_ident(name):
    """Quote a MySQL identifier with backticks, doubling embedded backticks.

    Only use on identifiers that have already been validated against the real
    schema (see ``_require_table``); the doubling then guarantees the name
    cannot break out of the identifier quoting.
    """
    if not isinstance(name, str) or not name:
        raise HTTPException(status_code=400, detail="Invalid SQL identifier")
    return "`" + name.replace("`", "``") + "`"


def _require_table(inspector, table_name):
    """Return ``table_name`` only when it names a real table (whitelist)."""
    if not isinstance(table_name, str) or table_name not in inspector.get_table_names():
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")
    return table_name

from data_access.base_knowledge_db import create_base_knowledge_table
from data_access.db_query_guide_db import create_db_query_guide_table
from data_access.doc_guide_db import create_doc_guide_table
from data_access.code_guide_db import create_code_guide_table
from data_access.graph_code_guide_db import create_graph_code_guide_table
from data_access.think_guide_db import create_think_guide_table
from data_access.brief_info_db import create_brief_info_table, init_brief_info

create_session_log_table()
create_observe_log_tables()
create_report_log_table()
create_db_query_guide_table()
create_brief_info_table()
init_brief_info()
if _ENABLE_BASE_KNOWLEDGE:
    create_base_knowledge_table()
    create_doc_guide_table()
    create_code_guide_table()
    create_graph_code_guide_table()
    create_think_guide_table()

# DATABASE_URL = config_data['mysql']
# engine = sqlalchemy.create_engine(DATABASE_URL)

app = FastAPI()


def _apply_meta(meta):
    if not isinstance(meta, dict):
        return
    apply_request_selection(
        meta.get("model"),
        meta.get("reasoning_effort"),
        meta.get("style"),
        meta.get("use_images"),
    )


def _apply_meta_json(raw):
    if not raw:
        return
    try:
        _apply_meta(json.loads(raw))
    except (TypeError, ValueError):
        pass


def _json_scalar(value):
    """Coerce a DataFrame cell into a type json.dumps(allow_nan=False) accepts.

    Starlette's JSONResponse uses plain ``json.dumps`` without a ``default``
    hook and with ``allow_nan=False``, so numpy scalars, datetimes, NaN/NaT and
    pandas NA all raise. Normalize them to native Python values (dates become
    ISO strings, missing/non-finite values become None).
    """
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (list, tuple, dict)):
        return value
    # numpy scalars (np.int64/np.float64/np.bool_/np.datetime64 ...) -> python natives
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    # Last-resort guard so an unexpected cell type can never raise on serialization.
    return str(value)


def _dataframe_to_records(df):
    """Convert a DataFrame to a JSON-serializable list of records."""
    if not isinstance(df, pd.DataFrame):
        return df
    return [
        {k: _json_scalar(v) for k, v in record.items()}
        for record in df.to_dict(orient="records")
    ]


@app.middleware("http")
async def unified_request_envelope(request: Request, call_next):
    """解析 {meta, data} 信封，兼容普通 JSON 主体。

    携带信封的请求（``{"meta": {...}, "data": ...}``）会被解包：meta 用于本次
    LLM 调用（模型/Depth/Style/图片），data 作为新主体转发给原接口。

    未携带信封的 JSON 主体原样透传。非 LLM 接口（如 sys-knowledge CRUD、
    doc-workspace、/api/models/* 等）直接发送普通 JSON，不应被强制要求信封；
    同时外部调用方既可以用普通 JSON，也可以用信封，两种方式都可用。
    """
    content_type = request.headers.get("content-type", "").lower()
    if request.method in ("POST", "PUT", "PATCH") and content_type.startswith("application/json"):
        body = await request.body()
        try:
            payload = json.loads(body) if body else None
        except (TypeError, ValueError):
            payload = None
        if (
            isinstance(payload, dict)
            and isinstance(payload.get("meta"), dict)
            and "data" in payload
        ):
            _apply_meta(payload["meta"])
            data = payload["data"]
            if isinstance(data, dict) and isinstance(data.get("conversation_history"), list):
                data["conversation_history"] = ingest_uploaded_images(data["conversation_history"])
            inner = json.dumps(data, ensure_ascii=False).encode("utf-8")
            request._body = inner
            headers = [
                (k, v) for k, v in request.scope["headers"]
                if k.lower() != b"content-length"
            ]
            headers.append((b"content-length", str(len(inner)).encode()))
            request.scope["headers"] = headers
            # ``request.headers`` was read at the top of this middleware, which
            # cached a ``Headers`` built from the *old* scope. Rebuild it so the
            # rewritten content-length is visible downstream, and drop any cached
            # parsed JSON so the new body is re-parsed.
            request._headers = Headers(scope=request.scope)
            if hasattr(request, "_json"):
                del request._json
    return await call_next(request)


@app.middleware("http")
async def limit_multipart_upload_size(request: Request, call_next):
    """Reject oversized multipart uploads before the body is parsed.

    Starlette's multipart parser spools uploads to disk, so a very large body is
    a DoS vector even though each handler also caps its own read. When the client
    provides a Content-Length, fail fast with HTTP 413 above the configured cap.
    """
    if request.method in ("POST", "PUT", "PATCH"):
        content_type = request.headers.get("content-type", "").lower()
        if content_type.startswith("multipart/form-data"):
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    too_large = int(content_length) > MAX_MULTIPART_BYTES
                except (TypeError, ValueError):
                    too_large = False
                if too_large:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": "Uploaded file exceeds the maximum allowed "
                            f"size of {MAX_MULTIPART_BYTES // (1024 * 1024)} MB"
                        },
                    )
    return await call_next(request)


import logging
import traceback

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f"Unhandled exception: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )

# 创建线程池，处理同步任务
executor = ThreadPoolExecutor(max_workers=10)


def _run_in_llm_context(func, *args):
    """把请求上下文（模型/Depth/Style）带入线程池中的 LLM 调用。

    必须在事件循环中调用：``contextvars.copy_context()`` 只会在事件循环任务里
    快照到本次请求的上下文；若在 executor 线程内调用，拷贝到的是该线程的空上
    下文，请求级模型/Depth/Style 选择会丢失。此函数返回一个无参可调用对象，
    在 worker 线程中通过 ``ctx.run`` 进入快照上下文执行 ``func``。
    """
    ctx = contextvars.copy_context()
    return lambda: ctx.run(func, *args)


# Upload size caps (bytes). ``UploadFile.read()`` materializes the whole body in
# memory, so every upload endpoint reads through ``_read_upload_limited``, which
# stops at the cap and rejects larger requests with HTTP 413.
MAX_CSV_UPLOAD_BYTES = 50 * 1024 * 1024      # /upload-csv/
MAX_DOC_UPLOAD_BYTES = 20 * 1024 * 1024      # /upload-txt/
MAX_COMMENT_CSV_BYTES = 5 * 1024 * 1024      # comment CSV import
# Highest per-endpoint cap; used as an early Content-Length guard so oversized
# multipart bodies are rejected before the parser spools them to disk.
MAX_MULTIPART_BYTES = max(
    MAX_CSV_UPLOAD_BYTES, MAX_DOC_UPLOAD_BYTES, MAX_COMMENT_CSV_BYTES
)


async def _read_upload_limited(file: UploadFile, max_bytes: int) -> bytes:
    """Read an UploadFile in bounded chunks, rejecting bodies over ``max_bytes``.

    A single ``await file.read()`` materializes the entire upload in memory, so
    an oversized file could exhaust memory. This reads at most ``max_bytes + 1``
    bytes across fixed-size chunks and raises HTTP 413 as soon as the cap is
    exceeded.
    """
    chunk_size = 1024 * 1024  # 1 MiB
    buffer = bytearray()
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    "Uploaded file exceeds the maximum allowed size of "
                    f"{max_bytes // (1024 * 1024)} MB"
                ),
            )
    return bytes(buffer)


STATIC_FOLDER = "tmp_imgs"
STATIC_PATH = f"/{STATIC_FOLDER}"
STATIC_DIR = os.path.realpath(STATIC_FOLDER)


@app.get(f"/{STATIC_FOLDER}/{{filename}}")
def read_static_file(request: Request, filename: str, download: str = None):
    safe_name = os.path.basename(filename.replace("\\", "/"))
    filepath = os.path.realpath(os.path.join(STATIC_FOLDER, safe_name))
    if not filepath.startswith(STATIC_DIR + os.sep) or not os.path.isfile(filepath):
        return JSONResponse(status_code=404, content={"error": "File not found"})
    content_type, _ = mimetypes.guess_type(filepath)
    if content_type is None:
        content_type = "application/octet-stream"
    headers = {}
    if download is not None:
        headers["Content-Disposition"] = f'attachment; filename="{safe_name}"'
    with open(filepath, "rb") as file:
        file_content = file.read()
    return Response(content=file_content, media_type=content_type, headers=headers)


class AgentInput(BaseModel):
    question: str
    tables: Optional[List[str]] = None
    session_id: Optional[str] = None
    selected_fields: Optional[Dict[str, Any]] = None
    selected_functions: Optional[List[str]] = None


class ReviewInput(BaseModel):
    question: str
    ans: str
    code: str
    session_id: Optional[str] = None


class UserInputLog(BaseModel):
    session_id: str
    cycle_index: int = 0
    user_input: str

# print(get_db())


@app.get("/api/config")
async def get_config():
    return JSONResponse(content={
        "enable_mcp": config_data.get("enable_mcp", True),
        "enable_base_knowledge": config_data.get("enable_base_knowledge", True),
        "enable_web_search": config_data.get("enable_web_search", True),
        "enable_fetch_url": config_data.get("enable_fetch_url", True),
        "enable_target_knowledge": config_data.get("enable_target_knowledge", False),
        "enable_edit": _ENABLE_EDIT,
        "models": list_model_configs(),
        "current_model": get_current_model_id(),
        "current_reasoning_effort": get_current_reasoning_effort(),
        "current_style": get_current_style(),
    })


@app.get("/api/models/")
async def get_models():
    return JSONResponse(content={
        "models": list_model_configs(),
        "current_model": get_current_model_id(),
        "current_reasoning_effort": get_current_reasoning_effort(),
        "current_style": get_current_style(),
    })


@app.get("/api/sessions/")
def get_sessions(request: Request, limit: int = 50):
    sessions = list_sessions(limit)
    return JSONResponse(content={"sessions": sessions})


@app.get("/api/db-overview/")
async def get_db_overview(request: Request):
    _require_edit_enabled()
    def _get_overview():
        import pandas as pd
        from sqlalchemy import text, inspect
        from sqlalchemy.exc import SQLAlchemyError
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        tables = []
        for table_name in table_names:
            try:
                table_comment = inspector.get_table_comment(table_name)
                columns = inspector.get_columns(table_name)
                cols = []
                for col in columns:
                    cols.append({"name": col["name"], "comment": col.get("comment", "") or ""})
                rows = []
                try:
                    with engine.connect() as conn:
                        df = pd.read_sql(text(f"SELECT * FROM {_quote_ident(table_name)} LIMIT 5"), conn)
                        for _, row in df.iterrows():
                            rows.append({k: str(v) if v is not None else "" for k, v in row.items()})
                except Exception:
                    pass
                tables.append({
                    "name": table_name,
                    "comment": (table_comment or {}).get("text", "") or "",
                    "columns": cols,
                    "rows": rows,
                })
            except SQLAlchemyError as e:
                tables.append({
                    "name": table_name,
                    "comment": "",
                    "columns": [],
                    "rows": [],
                })
        return {"tables": tables}
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, _get_overview)
    return JSONResponse(content=result)


class CommentUpdate(BaseModel):
    comment: str


@app.delete("/api/table/{table_name}")
async def drop_table(table_name: str):
    _require_edit_enabled()
    def _drop():
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        safe_table = _require_table(inspector, table_name)
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {_quote_ident(safe_table)}"))
            conn.commit()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(executor, _drop)
    return {"deleted": True, "table": table_name}


@app.get("/api/table-names/")
async def list_table_names():
    def _list():
        from sqlalchemy import inspect
        inspector = inspect(engine)
        return inspector.get_table_names()
    loop = asyncio.get_event_loop()
    names = await loop.run_in_executor(executor, _list)
    return {"tables": names}


@app.get("/api/table/{table_name}/export-data-csv")
async def export_table_data_csv(table_name: str):
    _require_edit_enabled()
    def _export():
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        safe_table = _require_table(inspector, table_name)
        df = pd.read_sql(text(f"SELECT * FROM {_quote_ident(safe_table)}"), engine)
        buf = io.BytesIO()
        df.to_csv(buf, index=False, encoding="utf-8-sig")
        buf.seek(0)
        return buf.getvalue()
    loop = asyncio.get_event_loop()
    csv_bytes = await loop.run_in_executor(executor, _export)
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{table_name}_data.csv"'}
    )


@app.get("/api/comment-manage/")
async def get_comment_manage():
    _require_edit_enabled()
    def _get():
        from sqlalchemy import inspect, text
        from sqlalchemy.exc import SQLAlchemyError
        from sqlalchemy.types import TypeEngine
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        tables = []
        for table_name in table_names:
            try:
                table_comment = inspector.get_table_comment(table_name)
                columns = inspector.get_columns(table_name)
                cols = []
                for col in columns:
                    col_type = col["type"]
                    if isinstance(col_type, TypeEngine):
                        col_type_str = str(col_type)
                    else:
                        col_type_str = str(col_type)
                    nullable = col.get("nullable", True)
                    default = col.get("default")
                    cols.append({
                        "name": col["name"],
                        "type": col_type_str,
                        "nullable": nullable,
                        "default": str(default) if default is not None else None,
                        "comment": col.get("comment", "") or "",
                    })
                tables.append({
                    "name": table_name,
                    "comment": (table_comment or {}).get("text", "") or "",
                    "columns": cols,
                })
            except SQLAlchemyError as e:
                tables.append({"name": table_name, "comment": "", "columns": []})
        return {"tables": tables}
    loop = asyncio.get_event_loop()
    return JSONResponse(content=await loop.run_in_executor(executor, _get))


@app.get("/api/comment-manage/{table_name}/export-csv")
async def export_comments_csv(table_name: str):
    _require_edit_enabled()
    def _export():
        from sqlalchemy import inspect
        from sqlalchemy.exc import SQLAlchemyError
        inspector = inspect(engine)
        safe_table = _require_table(inspector, table_name)
        table_comment = inspector.get_table_comment(safe_table)
        table_comment_text = (table_comment or {}).get("text", "") or ""
        columns = inspector.get_columns(safe_table)
        rows = []
        rows.append({"column_name": "__table_comment__", "comment": table_comment_text})
        for col in columns:
            rows.append({"column_name": col["name"], "comment": col.get("comment", "") or ""})
        df = pd.DataFrame(rows)
        buf = io.BytesIO()
        df.to_csv(buf, index=False, encoding="utf-8-sig")
        buf.seek(0)
        return buf.getvalue()
    loop = asyncio.get_event_loop()
    csv_bytes = await loop.run_in_executor(executor, _export)
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{table_name}_comments.csv"'}
    )


@app.post("/api/comment-manage/{table_name}/import-csv")
async def import_comments_csv(table_name: str, file: UploadFile = File(...)):
    _require_edit_enabled()
    if not file.filename or not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    content = await _read_upload_limited(file, MAX_COMMENT_CSV_BYTES)
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    def _import(bytes_content):
        from sqlalchemy import inspect
        from sqlalchemy.exc import SQLAlchemyError
        try:
            inspector = inspect(engine)
            if table_name not in inspector.get_table_names():
                return {"success": False, "error": f"Table '{table_name}' not found"}
            df = pd.read_csv(io.BytesIO(bytes_content))
            if "column_name" not in df.columns or "comment" not in df.columns:
                return {"success": False, "error": "CSV must contain 'column_name' and 'comment' columns"}
            columns_info = {c["name"]: c for c in inspector.get_columns(table_name)}
            errors = []
            for i, row in df.iterrows():
                line_no = i + 2
                col_name = str(row["column_name"]).strip()
                if not col_name:
                    continue
                if col_name not in columns_info and col_name != "__table_comment__":
                    errors.append(f"Row {line_no}: Unknown column '{col_name}'")
            if errors:
                return {"success": False, "error": f"Validation failed:\n" + "\n".join(errors)}
            with engine.connect() as conn:
                for i, row in df.iterrows():
                    col_name = str(row["column_name"]).strip()
                    comment = str(row["comment"]) if pd.notna(row.get("comment")) else ""
                    if not col_name:
                        continue
                    if col_name == "__table_comment__":
                        conn.exec_driver_sql(build_table_comment_sql(conn, table_name, comment))
                    elif col_name in columns_info:
                        conn.exec_driver_sql(build_column_comment_sql(conn, table_name, col_name, comment))
                conn.commit()
            return {
                "success": True,
                "table_comment_updated": True,
                "columns_updated": len(df) - (1 if "__table_comment__" in df["column_name"].values else 0)
            }
        except Exception as e:
            return {"success": False, "error": f"Import failed. The DB reports: {str(e)}"}
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, _import, content)
    return JSONResponse(content=result)


@app.put("/api/comment-manage/{table_name}/table-comment")
async def update_table_comment(table_name: str, entry: CommentUpdate):
    _require_edit_enabled()
    def _update():
        from sqlalchemy import inspect
        inspector = inspect(engine)
        safe_table = _require_table(inspector, table_name)
        with engine.connect() as conn:
            conn.exec_driver_sql(build_table_comment_sql(conn, safe_table, entry.comment))
            conn.commit()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(executor, _update)
    return {"table": table_name, "comment": entry.comment}


@app.put("/api/comment-manage/{table_name}/column/{column_name}/comment")
async def update_column_comment(table_name: str, column_name: str, entry: CommentUpdate):
    _require_edit_enabled()
    def _update():
        from sqlalchemy import inspect
        inspector = inspect(engine)
        safe_table = _require_table(inspector, table_name)
        columns = inspector.get_columns(safe_table)
        col_info = next((c for c in columns if c["name"] == column_name), None)
        if not col_info:
            raise HTTPException(status_code=404, detail=f"Column '{column_name}' not found in '{table_name}'")
        with engine.connect() as conn:
            conn.exec_driver_sql(build_column_comment_sql(conn, safe_table, col_info["name"], entry.comment))
            conn.commit()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(executor, _update)
    return {"table": table_name, "column": column_name, "comment": entry.comment}


@app.get("/api/session/{session_id}/history")
def get_session_history(request: Request, session_id: str):
    result = reconstruct_conversation_history(session_id)
    if result is None:
        return JSONResponse(
            status_code=404,
            content={"error": "Session not found"}
        )
    return JSONResponse(content=result)


@app.get("/api/session/{session_id}/generated-files")
def get_session_generated_files(request: Request, session_id: str):
    files = get_generated_files(session_id)
    return JSONResponse(content={"files": files})


@app.post("/api/log-user-input/")
def log_user_input(request: Request, user_input: UserInputLog):
    log_observe_cycle(
        user_input.session_id, user_input.cycle_index,
        "user", "input",
        user_decision=user_input.user_input[:2000],
    )
    return JSONResponse(content={"status": "ok"})








@app.post("/api/exe-sql/")
async def exe_sql(request: Request, user_input: AgentInput):
    if read_engine is None:
        raise HTTPException(
            status_code=503,
            detail="No read-only database is configured (mysql_readonly is missing)",
        )
    loop = asyncio.get_event_loop()
    ans = await loop.run_in_executor(executor, execute_select, read_engine, user_input.question)
    ans_str = await run_in_threadpool(str, ans)
    processed_data = {
        "ans": _dataframe_to_records(ans),
        "type": "success",
        "msg": "处理成功",
        "session_id": user_input.session_id or ""
    }
    await run_in_threadpool(
        record_session_operation,
        user_input.session_id, request.url.path,
        user_input.model_dump_json(), ans_str, "", "success", "处理成功",
    )
    await run_in_threadpool(
        log_observe_cycle,
        user_input.session_id or "", 0, "execute", "exe_sql",
        exec_code=user_input.question,
        exec_result=ans_str[:10000],
    )

    return JSONResponse(content=processed_data)


from agent.tools.copilot.utils.read_db import get_rows_from_all_tables, get_table_comments_dict, execute_select, \
    get_all_comments
from agent.tools.copilot.sql_code import filter_db_fields, filter_db_fields_stream
from agent.tools.get_function_info import filter_functions_stream
from agent.tools.tools_def import engine, read_engine, read_only_engine, llm


@app.post("/api/db-slice/")
async def db_slice(request: Request):
    loop = asyncio.get_event_loop()
    first_five_rows = await loop.run_in_executor(
        executor,
        get_rows_from_all_tables,
        read_only_engine,
        None,
        5
    )
    # 用 _json_scalar 归一化每个单元格：NaN/NaT/numpy 标量/Decimal/datetime
    # 等都无法被 JSONResponse 的 json.dumps(allow_nan=False) 序列化，直接输出会 500。
    first_five_rows_json = {
        table_name: {
            "columns": rows.columns.tolist(),
            "data": [[_json_scalar(item) for item in row] for row in rows.values.tolist()]
        }
        for table_name, rows in first_five_rows.items()
    }

    processed_data = {
        "ans": first_five_rows_json,
        "type": "success",
        "msg": "处理成功"
    }

    return JSONResponse(content=processed_data)


@app.post("/api/db-comments/")
async def db_comments(request: Request):
    loop = asyncio.get_event_loop()
    all_comments = await loop.run_in_executor(executor, get_all_comments, read_only_engine, None)
    comments_json = {}
    for table_name, comments in all_comments.items():
        comments_json[table_name] = {
            "table_comment": comments.get('table_comment', ''),
            "columns": comments.get('columns', {})
        }
    processed_data = {
        "ans": comments_json,
        "type": "success",
        "msg": "Table comments and column comments fetched successfully"
    }
    return JSONResponse(content=processed_data)


@app.post("/api/table-comments/")
async def table_comments(request: Request):
    loop = asyncio.get_event_loop()
    table_comments = await loop.run_in_executor(executor, get_table_comments_dict, read_only_engine, None)
    processed_data = {
        "ans": table_comments,
        "type": "success",
        "msg": "Table comments fetched successfully"
    }
    return JSONResponse(content=processed_data)


@app.post("/api/filter-db-fields/")
async def filter_db_fields_api(request: Request, user_input: AgentInput):
    loop = asyncio.get_event_loop()

    def _timed_filter_db_fields(question, engine_, llm_, tables):
        with perf_context("/api/filter-db-fields/"):
            return filter_db_fields(question, engine_, llm_, tables)

    selected_fields = await loop.run_in_executor(
        executor,
        _run_in_llm_context(
            _timed_filter_db_fields,
            user_input.question,
            read_only_engine,
            llm,
            user_input.tables,
        ),
    )
    if selected_fields is not None:
        processed_data = {
            "ans": selected_fields,
            "type": "success",
            "msg": "Fields filtered successfully"
        }
    else:
        processed_data = {
            "ans": {},
            "type": "error",
            "msg": "Fields filtering failed"
        }
    return JSONResponse(content=processed_data)


@perf_api("/api/filter-db-fields/stream/")
def _event_stream_filter_db_fields(question: str, tables: Optional[List[str]], session_id: str = "", request_url: str = "", request_json: str = ""):
    full_content = ""
    prompt_length = 0
    for event in filter_db_fields_stream(question, read_only_engine, llm, tables):
        if event.get("type") == "chunk":
            full_content += event.get("content", "")
        if event.get("type") in ("done", "error"):
            prompt_length = event.get("prompt_length", 0)
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    record_session_operation(session_id, request_url, request_json, ans=full_content, result_type="success", prompt_length=prompt_length)


@app.post("/api/filter-db-fields/stream/")
async def filter_db_fields_stream_api(request: Request, user_input: AgentInput):
    return StreamingResponse(
        _event_stream_filter_db_fields(user_input.question, user_input.tables, user_input.session_id or "", request.url.path, user_input.model_dump_json()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@perf_api("/api/filter-functions/stream/")
def _event_stream_filter_functions(question: str, session_id: str = "", request_url: str = "", request_json: str = ""):
    full_content = ""
    prompt_length = 0
    for event in filter_functions_stream(question, llm):
        if event.get("type") == "chunk":
            full_content += event.get("content", "")
        if event.get("type") == "done":
            prompt_length = event.get("prompt_length", 0)
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    record_session_operation(session_id, request_url, request_json, ans=full_content, result_type="success", prompt_length=prompt_length)


@app.post("/api/filter-functions/stream/")
async def filter_functions_stream_api(request: Request, user_input: AgentInput):
    return StreamingResponse(
        _event_stream_filter_functions(user_input.question, user_input.session_id or "", request.url.path, user_input.model_dump_json()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.post("/upload-csv/")
async def upload_csv(
        file: UploadFile = File(..., description="CSV file"),
        table_name: str = Form("uploaded_data")
):
    _require_edit_enabled()
    if not file.filename or not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    content = await _read_upload_limited(file, MAX_CSV_UPLOAD_BYTES)
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, process_csv_to_database, content, table_name)
    return JSONResponse(content=result)


@app.post("/upload-txt/")
async def upload_txt(
        file: UploadFile = File(..., description="支持 txt, doc, docx, pdf 文件"),
        table_name: str = Form("uploaded_data"),
        meta: Optional[str] = Form(None)
):
    _require_edit_enabled()
    _apply_meta_json(meta)
    allowed_extensions = {'.txt', '.doc', '.docx', '.pdf'}
    file_extension = os.path.splitext(file.filename or "")[1].lower()

    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Only txt, doc, docx, pdf files are supported"
        )

    try:
        content = await _read_upload_limited(file, MAX_DOC_UPLOAD_BYTES)
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        loop = asyncio.get_event_loop()
        extracted_text = await loop.run_in_executor(executor, process_file_content, content, file_extension)

        def _timed_data_comment(text, table):
            with perf_context("/upload-txt/"):
                return get_llm_data_comment(text, table)

        comment_applied = await loop.run_in_executor(
            executor,
            _run_in_llm_context(_timed_data_comment, extracted_text, table_name),
        )
        comment_applied = bool(comment_applied)

        preview = extracted_text[:500] + "..." if len(extracted_text) > 500 else extracted_text
        if comment_applied:
            result = {
                "status": "success",
                "success": True,
                "message": f"Comments were generated and applied to table '{table_name}'.",
                "table_name": table_name,
                "comment_applied": True,
                "extracted_text_length": len(extracted_text),
                "preview": preview,
            }
        else:
            error = (
                f"No comments were applied to table '{table_name}'. "
                "Make sure the table exists and that the model returned valid comment JSON."
            )
            result = {
                "status": "error",
                "success": False,
                "error": error,
                "message": error,
                "table_name": table_name,
                "comment_applied": False,
                "extracted_text_length": len(extracted_text),
                "preview": preview,
            }
    except HTTPException:
        # Preserve client errors raised below (413 oversize, 400 empty file,
        # 400 unsupported/unparseable document) instead of collapsing them all
        # into an opaque 500.
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"File processing error: {str(e)}")
    return JSONResponse(content=result)




@perf_api("/api/generate-and-execute/stream/")
def _event_stream_generate_and_execute(question: str, tables: Optional[List[str]], selected_fields: Optional[Dict[str, Any]] = None, selected_functions: Optional[List[str]] = None, session_id: str = "", request_url: str = "", request_json: str = ""):
    full_code = ""
    full_ans = ""
    exec_error = None
    exec_error_kind = ""
    for event in generate_and_execute_stream(question, tables, selected_fields=selected_fields, selected_functions=selected_functions):
        sub_type = event.get("sub_type")
        if sub_type == "code_chunk":
            if exec_error:
                full_code = ""
                full_ans = ""
                exec_error = None
                exec_error_kind = ""
            full_code += event.get("content", "")
        if sub_type == "code_complete":
            full_code = event.get("content", full_code)
        if sub_type == "exec_chunk":
            full_ans += event.get("content", "")
        if sub_type in ("code_exe_error", "code_gen_error"):
            exec_error = event.get("content", "")
            if event.get("error_kind"):
                exec_error_kind = event["error_kind"]
        if event.get("type") == "done" and event.get("sub_phase") == "exec":
            full_code = event.get("code", full_code)
            full_ans = event.get("content", full_ans)
        if event.get("type") == "error":
            exec_error = event.get("error") or event.get("content", exec_error or "code generation/execution failed")
            if event.get("error_kind"):
                exec_error_kind = event["error_kind"]
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    if exec_error:
        record_msg = exec_error
        if exec_error_kind and not record_msg.startswith(f"[{exec_error_kind}]"):
            record_msg = f"[{exec_error_kind}] {record_msg}"
        record_session_operation(session_id, request_url, request_json, ans=full_ans, code=full_code, result_type="error", msg=record_msg[:500])
    else:
        record_session_operation(session_id, request_url, request_json, ans=full_ans, code=full_code, result_type="success")



class CodeInput(BaseModel):
    code: str
    session_id: Optional[str] = None


@app.post("/api/generate-and-execute/stream/")
async def generate_and_execute_stream_api(request: Request, user_input: AgentInput):
    return StreamingResponse(
        _event_stream_generate_and_execute(user_input.question, user_input.tables, user_input.selected_fields, user_input.selected_functions, user_input.session_id or "", request.url.path, user_input.model_dump_json()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )



@perf_api("/api/plain-chat/stream/")
def _event_stream_plain_chat(question: str, tables=None, selected_fields=None, session_id: str = "", request_url: str = "", request_json: str = ""):
    full_content = ""
    prompt_length = 0
    for chunk in get_plain_chat_stream(question, tables, selected_fields):
        if isinstance(chunk, dict) and "prompt_length" in chunk:
            prompt_length = chunk["prompt_length"]
            continue
        if not chunk:
            continue
        full_content += chunk
        yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'type': 'done', 'content': ''}, ensure_ascii=False)}\n\n"
    record_session_operation(session_id, request_url, request_json, ans=full_content, result_type="success", prompt_length=prompt_length)


@app.post("/api/plain-chat/stream/")
async def plain_chat_stream(request: Request, user_input: AgentInput):
    return StreamingResponse(
        _event_stream_plain_chat(user_input.question, user_input.tables, user_input.selected_fields, user_input.session_id or "", request.url.path, user_input.model_dump_json()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/api/tools/functions")
async def list_python_functions():
    def _list():
        from agent.tools.get_function_info import FUNCTION_DICT, FUNCTION_DESCRIPTION, CUSTOM_FUNC_NAMES
        result = []
        for name, func in FUNCTION_DICT.items():
            if name in CUSTOM_FUNC_NAMES:
                continue
            result.append({
                "name": name,
                "description": FUNCTION_DESCRIPTION.get(name, func.__doc__ or ""),
                "doc": func.__doc__ or ""
            })
        return result
    loop = asyncio.get_event_loop()
    return JSONResponse(content=await loop.run_in_executor(executor, _list))


@app.get("/api/tools/custom-functions")
async def list_custom_functions():
    def _list():
        from agent.tools.get_function_info import FUNCTION_DICT, FUNCTION_DESCRIPTION, CUSTOM_FUNC_NAMES
        result = []
        for name, func in FUNCTION_DICT.items():
            if name not in CUSTOM_FUNC_NAMES:
                continue
            result.append({
                "name": name,
                "description": FUNCTION_DESCRIPTION.get(name, func.__doc__ or ""),
                "doc": func.__doc__ or ""
            })
        return result
    loop = asyncio.get_event_loop()
    return JSONResponse(content=await loop.run_in_executor(executor, _list))


@app.get("/api/tools/mcp")
async def list_mcp_tools():
    from agent.tools.mcp_client import load_mcp_servers, MCPClient

    try:
        servers = load_mcp_servers()
    except Exception as e:
        print(f"[WARNING] Failed to load MCP servers: {e}")
        return JSONResponse(content=[])
    results = []

    async def _fetch(srv):
        name = srv.get("name", "")
        desc = srv.get("description", "")
        url = srv.get("url", "")
        info = {"server_name": name, "server_description": desc, "url": url, "tools": [], "error": None}
        try:
            loop = asyncio.get_event_loop()
            def _run():
                with MCPClient(srv) as client:
                    return client.list_tools()
            tools = await asyncio.wait_for(
                loop.run_in_executor(executor, _run),
                timeout=35
            )
            for t in tools:
                params = t.get("inputSchema", {}).get("properties", {})
                param_names = list(params.keys()) if params else []
                info["tools"].append({
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "parameters": param_names
                })
        except asyncio.TimeoutError:
            info["error"] = "Connection timed out after 35 seconds"
        except Exception as e:
            info["error"] = str(e)
        results.append(info)

    await asyncio.gather(*[_fetch(srv) for srv in servers])
    return JSONResponse(content=results)


from agent.think import router as think_router
from agent.act import router as act_router
from agent.observe import router as observe_router
from agent.action import router as action_router
from agent.document_generator import router as document_router
from agent.sys_knowledge_router import router as sys_knowledge_router
app.include_router(think_router)
app.include_router(act_router)
app.include_router(observe_router)
app.include_router(action_router)
app.include_router(document_router)
app.include_router(sys_knowledge_router)


def _check_mcp_servers():
    try:
        from agent.tools.mcp_client import load_mcp_servers
        servers = load_mcp_servers()
    except Exception as e:
        # MCP is optional; a missing/invalid config must never block startup.
        print(f"[WARNING] Skipping MCP server check: {e}")
        return
    if not servers:
        return
    import socket
    for srv in servers:
        name = srv.get("name", "?")
        transport = srv.get("transport", "stdio")
        if transport != "sse":
            continue
        url = srv.get("url", "")
        if not url:
            continue
        host, port = _parse_host_port(url)
        if host and port:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            try:
                s.connect((host, port))
                s.close()
            except Exception:
                print(f"[WARNING] MCP server '{name}' ({url}) is not running")


def _parse_host_port(url: str):
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.hostname and parsed.port:
        return parsed.hostname, parsed.port
    if parsed.hostname and parsed.scheme == "http":
        return parsed.hostname, 80
    if parsed.hostname and parsed.scheme == "https":
        return parsed.hostname, 443
    return None, None


_check_mcp_servers()

if __name__ == "__main__":
    try:
        uvicorn.run(app, host=config_data['server_host'], port=config_data['server_port'], loop="asyncio")
    finally:
        executor.shutdown(wait=True)