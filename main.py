import os
os.environ['MPLBACKEND'] = 'Agg'

import asyncio
import io
import json
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict, Any
import pandas as pd
import sqlalchemy
import uvicorn
from fastapi import FastAPI, Request, Form
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi import File, UploadFile, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.responses import JSONResponse


from agent.plain_chat import get_plain_chat, get_plain_chat_stream
from agent.data_comment import get_llm_data_comment

from data_access.insert_data_from_csv import process_csv_to_database
from data_access.read_db import get_all_comments_from_table
from data_access.db_conn import engine
from utils.get_config import config_data

from agent.agent import  generate_and_execute_stream, get_db
from utils.process_file import process_file_content
from data_access.session_log import record_session_operation, create_session_log_table
from data_access.observe_log import (
    create_observe_log_tables, log_observe_cycle, log_observe_session,
    list_sessions, reconstruct_conversation_history
)
from data_access.report_log import create_report_log_table, get_generated_files
_ENABLE_BASE_KNOWLEDGE = config_data.get('enable_base_knowledge', True)

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

STATIC_FOLDER = config_data.get("static_folder", "tmp_imgs")
STATIC_PATH = f"/{STATIC_FOLDER}"


# http://127.0.0.1:8003/tmp_imgs/mlkjcvep.png
@app.get(f"/{STATIC_FOLDER}/{{filename}}")
async def read_static_file(request: Request, filename: str, download: str = None):
    filepath = os.path.join(STATIC_FOLDER, filename)
    if os.path.isfile(filepath):
        content_type, _ = mimetypes.guess_type(filepath)
        if content_type is None:
            content_type = "application/octet-stream"
        headers = {}
        if download is not None:
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        with open(filepath, "rb") as file:
            file_content = file.read()
        return Response(content=file_content, media_type=content_type, headers=headers)
    else:
        return {"error": "File not found"}


class AgentInput(BaseModel):
    question: str
    tables: Optional[List[str]] = None
    session_id: Optional[str] = None
    selected_fields: Optional[Dict[str, Any]] = None
    selected_functions: Optional[List[str]] = None


class AgentInputDict(BaseModel):
    question: str
    data: dict
    session_id: Optional[str] = None


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


@app.get("/api/sessions/")
async def get_sessions(request: Request, limit: int = 50):
    sessions = list_sessions(limit)
    return JSONResponse(content={"sessions": sessions})


@app.get("/api/db-overview/")
async def get_db_overview(request: Request):
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
                        df = pd.read_sql(text(f"SELECT * FROM `{table_name}` LIMIT 5"), conn)
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
    def _drop():
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        if not inspector.has_table(table_name):
            raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{table_name}`"))
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
    def _export():
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        if not inspector.has_table(table_name):
            raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")
        df = pd.read_sql(text(f"SELECT * FROM `{table_name}`"), engine)
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
    def _export():
        from sqlalchemy import inspect
        from sqlalchemy.exc import SQLAlchemyError
        inspector = inspect(engine)
        if not inspector.has_table(table_name):
            raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")
        table_comment = inspector.get_table_comment(table_name)
        table_comment_text = (table_comment or {}).get("text", "") or ""
        columns = inspector.get_columns(table_name)
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
    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    def _import(bytes_content):
        from sqlalchemy import inspect, text
        from sqlalchemy.exc import SQLAlchemyError
        try:
            inspector = inspect(engine)
            if not inspector.has_table(table_name):
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
                        escaped = comment.replace("'", "''")
                        conn.execute(text(f"ALTER TABLE `{table_name}` COMMENT = '{escaped}'"))
                    elif col_name in columns_info:
                        col_info = columns_info[col_name]
                        col_type = col_info["type"]
                        nullable = col_info.get("nullable", True)
                        default = col_info.get("default")
                        escaped = comment.replace("'", "''")
                        nullable_str = "NULL" if nullable else "NOT NULL"
                        default_str = f"DEFAULT {default}" if default is not None else ""
                        sql = f"ALTER TABLE `{table_name}` MODIFY COLUMN `{col_name}` {col_type} {nullable_str} {default_str} COMMENT '{escaped}'"
                        conn.execute(text(sql))
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
    def _update():
        from sqlalchemy import text
        escaped = entry.comment.replace("'", "''")
        with engine.connect() as conn:
            conn.execute(text(f"ALTER TABLE `{table_name}` COMMENT = '{escaped}'"))
            conn.commit()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(executor, _update)
    return {"table": table_name, "comment": entry.comment}


@app.put("/api/comment-manage/{table_name}/column/{column_name}/comment")
async def update_column_comment(table_name: str, column_name: str, entry: CommentUpdate):
    def _update():
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        columns = inspector.get_columns(table_name)
        col_info = next((c for c in columns if c["name"] == column_name), None)
        if not col_info:
            raise HTTPException(status_code=404, detail=f"Column '{column_name}' not found in '{table_name}'")
        col_type = col_info["type"]
        nullable = col_info.get("nullable", True)
        default = col_info.get("default")
        escaped = entry.comment.replace("'", "''")
        nullable_str = "NULL" if nullable else "NOT NULL"
        default_str = f"DEFAULT {default}" if default is not None else ""
        sql = f"ALTER TABLE `{table_name}` MODIFY COLUMN `{column_name}` {col_type} {nullable_str} {default_str} COMMENT '{escaped}'"
        with engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(executor, _update)
    return {"table": table_name, "column": column_name, "comment": entry.comment}


@app.get("/api/session/{session_id}/history")
async def get_session_history(request: Request, session_id: str):
    result = reconstruct_conversation_history(session_id)
    if result is None:
        return JSONResponse(
            status_code=404,
            content={"error": "Session not found"}
        )
    return JSONResponse(content=result)


@app.get("/api/session/{session_id}/generated-files")
async def get_session_generated_files(request: Request, session_id: str):
    files = get_generated_files(session_id)
    return JSONResponse(content={"files": files})


@app.post("/api/log-user-input/")
async def log_user_input(request: Request, user_input: UserInputLog):
    log_observe_cycle(
        user_input.session_id, user_input.cycle_index,
        "user", "input",
        user_decision=user_input.user_input[:2000],
    )
    return JSONResponse(content={"status": "ok"})








@app.post("/api/exe-sql/")
async def exe_sql(request: Request, user_input: AgentInput):
    loop = asyncio.get_event_loop()
    ans = await loop.run_in_executor(executor, execute_select, engine, user_input.question)
    processed_data = {
        "ans": ans,
        "type": "success",
        "msg": "处理成功",
        "session_id": user_input.session_id or ""
    }
    record_session_operation(
        user_input.session_id, request.url.path,
        user_input.model_dump_json(), str(ans), "", "success", "处理成功"
    )
    log_observe_cycle(
        user_input.session_id or "", 0, "execute", "exe_sql",
        exec_code=user_input.question,
        exec_result=str(ans)[:10000],
    )

    return JSONResponse(content=processed_data)


@app.post("/api/get-graph/")
async def get_graph_api(request: Request, user_input: AgentInputDict):
    df = pd.DataFrame.from_dict(user_input.data)
    loop = asyncio.get_event_loop()
    ans = await loop.run_in_executor(executor, draw_graph, user_input.question, df)
    if ans:
        processed_data = {
            "question": user_input.question,
            "ans": ans,
            "type": "success",
"msg": "Processed successfully",
            "session_id": user_input.session_id or ""
        }
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.model_dump_json(), ans, "", "success", "处理成功"
        )
    else:
        processed_data = {
            "question": user_input.question,
            "ans": "",
            "type": "error",
            "msg": "Processing failed, please rephrase your question",
            "session_id": user_input.session_id or ""
        }
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.model_dump_json(), "", "", "error", "处理失败，请换个问法吧"
        )
    return JSONResponse(content=processed_data)


from agent.tools.copilot.utils.read_db import get_rows_from_all_tables, get_table_comments_dict, execute_select, \
    get_all_comments
from agent.tools.copilot.sql_code import filter_db_fields, filter_db_fields_stream
from agent.tools.get_function_info import filter_functions_stream
from agent.tools.tools_def import engine, llm, draw_graph


@app.post("/api/db-slice/")
async def db_slice(request: Request):
    loop = asyncio.get_event_loop()
    first_five_rows = await loop.run_in_executor(
        executor,
        get_rows_from_all_tables,
        engine,
        None,
        5
    )
    from datetime import date, datetime
    def convert_date(obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return obj

    first_five_rows_json = {
        table_name: {
            "columns": rows.columns.tolist(),
            "data": [[convert_date(item) for item in row] for row in rows.values.tolist()]
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
    all_comments = await loop.run_in_executor(executor, get_all_comments, engine, None)
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
    table_comments = await loop.run_in_executor(executor, get_table_comments_dict, engine, None)
    processed_data = {
        "ans": table_comments,
        "type": "success",
        "msg": "Table comments fetched successfully"
    }
    return JSONResponse(content=processed_data)


@app.post("/api/filter-db-fields/")
async def filter_db_fields_api(request: Request, user_input: AgentInput):
    loop = asyncio.get_event_loop()
    selected_fields = await loop.run_in_executor(
        executor,
        filter_db_fields,
        user_input.question,
        engine,
        llm,
        user_input.tables
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


def _event_stream_filter_db_fields(question: str, tables: Optional[List[str]], session_id: str = "", request_url: str = "", request_json: str = ""):
    full_content = ""
    prompt_length = 0
    for event in filter_db_fields_stream(question, engine, llm, tables):
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
    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, process_csv_to_database, content, table_name)
    return JSONResponse(content=result)


@app.post("/upload-txt/")
async def upload_txt(
        file: UploadFile = File(..., description="支持 txt, doc, docx, pdf 文件"),
        table_name: str = Form("uploaded_data")
):
    allowed_extensions = {'.txt', '.doc', '.docx', '.pdf'}
    file_extension = file.filename[file.filename.rfind('.'):].lower()

    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Only txt, doc, docx, pdf files are supported"
        )

    try:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        loop = asyncio.get_event_loop()
        extracted_text = await loop.run_in_executor(executor, process_file_content, content, file_extension)
        result = await loop.run_in_executor(executor, get_llm_data_comment, extracted_text, table_name)

        result = {
            "status": "success",
            "table_name": table_name,
            "extracted_text_length": len(extracted_text),
            "preview": extracted_text[:500] + "..." if len(extracted_text) > 500 else extracted_text
        }
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"File processing error: {str(e)}")
    return JSONResponse(content=result)




def _event_stream_generate_and_execute(question: str, tables: Optional[List[str]], selected_fields: Optional[Dict[str, Any]] = None, selected_functions: Optional[List[str]] = None, session_id: str = "", request_url: str = "", request_json: str = ""):
    full_code = ""
    full_ans = ""
    exec_error = None
    for event in generate_and_execute_stream(question, tables, selected_fields=selected_fields, selected_functions=selected_functions):
        if event.get("sub_type") == "code_chunk":
            full_code += event.get("content", "")
        if event.get("sub_type") == "exec_chunk":
            full_ans += event.get("content", "")
        if event.get("sub_type") == "code_gen_error" and event.get("phase") == "exec":
            exec_error = event.get("content", "")
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    if exec_error:
        record_session_operation(session_id, request_url, request_json, ans=full_ans, code=full_code, result_type="error", msg=exec_error[:500])
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



def _event_stream_plain_chat(question: str, tables=None, selected_fields=None, session_id: str = "", request_url: str = "", request_json: str = ""):
    full_content = ""
    prompt_length = 0
    for chunk in get_plain_chat_stream(question, tables, selected_fields):
        if isinstance(chunk, dict) and "prompt_length" in chunk:
            prompt_length = chunk["prompt_length"]
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
        from agent.tools.get_function_info import FUNCTION_DICT, FUNCTION_DESCRIPTION
        result = []
        for name, func in FUNCTION_DICT.items():
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

    servers = load_mcp_servers()
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
        if not servers:
            return
        import socket
        for srv in servers:
            name = srv.get("name", "?")
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
    except ImportError:
        pass


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