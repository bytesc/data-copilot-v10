import asyncio
import json
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict, Any
import pandas as pd
import sqlalchemy
import uvicorn
import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi import File, UploadFile, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.responses import JSONResponse

from agent.cot_chat import get_cot_chat
from agent.plain_chat import get_plain_chat, get_plain_chat_stream
from agent.data_comment import get_llm_data_comment
from agent.step_chat import get_step_chat, get_step_chat_stream
from data_access.insert_data_from_csv import process_csv_to_database
from utils.get_config import config_data

from agent.agent import exe_cot_code, get_cot_code, cot_agent, generate_code_stream, execute_code_stream, generate_and_execute_stream, get_db
from agent.summary import get_ans_summary
from agent.ans_review import get_ans_review
from utils.process_file import process_file_content
from data_access.session_log import record_session_operation, create_session_log_table
from data_access.observe_log import (
    create_observe_log_tables, log_observe_cycle, log_observe_session
)

# 启动时确保会话操作记录表已创建
create_session_log_table()
create_observe_log_tables()

# DATABASE_URL = config_data['mysql']
# engine = sqlalchemy.create_engine(DATABASE_URL)

app = FastAPI()

# 创建线程池，处理同步任务
executor = ThreadPoolExecutor(max_workers=10)

STATIC_FOLDER = "tmp_imgs"
STATIC_PATH = f"/{STATIC_FOLDER}"


# http://127.0.0.1:8003/tmp_imgs/mlkjcvep.png
@app.get(f"/{STATIC_FOLDER}/{{filename}}")
async def read_static_file(request: Request, filename: str):
    filepath = os.path.join(STATIC_FOLDER, filename)
    if os.path.isfile(filepath):
        # 猜测文件的MIME类型
        content_type, _ = mimetypes.guess_type(filepath)
        if content_type is None:
            content_type = "application/octet-stream"  # 默认为二进制流，如果无法确定类型
        # 读取文件内容
        with open(filepath, "rb") as file:
            file_content = file.read()
        # 返回Response对象，文件内容作为字节流发送
        return Response(content=file_content, media_type=content_type)
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


# print(get_db())

@app.post("/api/ask-agent/")
async def ask_agent(request: Request, user_input: AgentInput):
    loop = asyncio.get_event_loop()
    ans, code = await loop.run_in_executor(
        executor,
        cot_agent,
        user_input.question,
        user_input.tables,
        True,
        2,
        5,
        user_input.selected_fields
    )
    print(ans)
    if ans:
        processed_data = {
            "question": user_input.question,
            "ans": ans,
            "code": code,
            "type": "success",
            "msg": "处理成功",
            "session_id": user_input.session_id or ""
}
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.question, "", "", "error", "处理失败，请换个问法吧", prompt_length=len(user_input.question)
        )
    else:
        processed_data = {
            "question": user_input.question,
            "ans": "",
            "code": "",
            "type": "error",
            "msg": "处理失败，请换个问法吧",
            "session_id": user_input.session_id or ""
        }
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.question, "", "", "error", "处理失败，请换个问法吧"
        )
    return JSONResponse(content=processed_data)


@app.post("/api/exe-code/")
async def exe_code(request: Request, user_input: AgentInput):
    loop = asyncio.get_event_loop()
    ans = await loop.run_in_executor(executor, exe_cot_code, user_input.question)
    print(ans)
    if ans:
        processed_data = {
            "question": user_input.question,
            "ans": ans,
            "type": "success",
            "msg": "处理成功",
            "session_id": user_input.session_id or ""
        }
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.question, ans, "", "success", "处理成功"
        )
    else:
        processed_data = {
            "question": user_input.question,
            "ans": "",
            "type": "error",
            "msg": "处理失败，请换个问法吧",
            "session_id": user_input.session_id or ""
        }
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.question, "", "", "error", "处理失败，请换个问法吧"
        )
    return JSONResponse(content=processed_data)


@app.post("/api/get-code/")
async def get_code(request: Request, user_input: AgentInput):
    loop = asyncio.get_event_loop()
    code = await loop.run_in_executor(executor, get_cot_code, user_input.question)
    print(code)
    if code:
        processed_data = {
            "question": user_input.question,
            "code": code,
            "type": "success",
            "msg": "处理成功",
            "session_id": user_input.session_id or ""
        }
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.question, "", code, "success", "处理成功"
        )
    else:
        processed_data = {
            "question": user_input.question,
            "code": "",
            "type": "error",
            "msg": "处理失败，请换个问法吧",
            "session_id": user_input.session_id or ""
        }
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.question, "", "", "error", "处理失败，请换个问法吧"
        )
    return JSONResponse(content=processed_data)


@app.post("/api/review/")
async def get_code(request: Request, user_input: ReviewInput):
    loop = asyncio.get_event_loop()
    ans = await loop.run_in_executor(
        executor,
        get_ans_review,
        user_input.question,
        user_input.ans,
        user_input.code
    )
    print(ans)
    if ans:
        processed_data = {
            "question": user_input.question,
            "ans": ans,
            "type": "success",
            "msg": "处理成功",
            "session_id": user_input.session_id or ""
        }
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.question, ans, "", "success", "处理成功"
        )
    else:
        processed_data = {
            "question": user_input.question,
            "ans": "",
            "type": "error",
            "msg": "处理失败，请换个问法吧",
            "session_id": user_input.session_id or ""
        }
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.question, "", "", "error", "处理失败，请换个问法吧"
        )
    return JSONResponse(content=processed_data)


@app.post("/api/agent-summary/")
async def agent_summary(request: Request, user_input: AgentInput):
    loop = asyncio.get_event_loop()
    ans = await loop.run_in_executor(executor, get_ans_summary, user_input.question)
    print(ans)
    if ans:
        processed_data = {
            "question": user_input.question,
            "ans": ans,
            "type": "success",
            "msg": "处理成功",
            "session_id": user_input.session_id or ""
        }
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.question, ans, "", "success", "处理成功"
        )
    else:
        processed_data = {
            "question": user_input.question,
            "ans": "",
            "type": "error",
            "msg": "处理失败，请换个问法吧",
            "session_id": user_input.session_id or ""
        }
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.question, "", "", "error", "处理失败，请换个问法吧"
        )
    return JSONResponse(content=processed_data)


@app.post("/api/cot-chat/")
async def cot_chat(request: Request, user_input: AgentInput):
    loop = asyncio.get_event_loop()
    ans = await loop.run_in_executor(executor, get_cot_chat, user_input.question)
    print(ans)
    if ans:
        processed_data = {
            "question": user_input.question,
            "ans": ans,
            "type": "success",
            "msg": "处理成功",
            "session_id": user_input.session_id or ""
        }
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.question, ans, "", "success", "处理成功"
        )
    else:
        processed_data = {
            "question": user_input.question,
            "ans": "",
            "type": "error",
            "msg": "处理失败，请换个问法吧",
            "session_id": user_input.session_id or ""
        }
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.question, "", "", "error", "处理失败，请换个问法吧"
        )
    return JSONResponse(content=processed_data)


@app.post("/api/step-chat/")
async def step_chat(request: Request, user_input: AgentInput):
    loop = asyncio.get_event_loop()
    ans = await loop.run_in_executor(executor, get_step_chat, user_input.question, user_input.tables, user_input.selected_fields)
    print(ans)
    print(user_input.session_id)
    if ans:
        processed_data = {
            "question": user_input.question,
            "ans": ans,
            "code": "",
            "type": "success",
            "msg": "处理成功",
            "session_id": user_input.session_id or ""
        }
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.question, ans, "", "success", "处理成功"
        )
    else:
        processed_data = {
            "question": user_input.question,
            "ans": "",
            "code": "",
            "type": "error",
            "msg": "处理失败，请换个问法吧",
            "session_id": user_input.session_id or ""
        }
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.question, "", "", "error", "处理失败，请换个问法吧"
        )
    return JSONResponse(content=processed_data)


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
        user_input.question, str(ans), "", "success", "处理成功"
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
            "msg": "处理成功",
            "session_id": user_input.session_id or ""
        }
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.question, ans, "", "success", "处理成功"
        )
    else:
        processed_data = {
            "question": user_input.question,
            "ans": "",
            "type": "error",
            "msg": "处理失败，请换个问法吧",
            "session_id": user_input.session_id or ""
        }
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.question, "", "", "error", "处理失败，请换个问法吧"
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
        "msg": "获取表注释和列注释成功"
    }
    return JSONResponse(content=processed_data)


@app.post("/api/table-comments/")
async def table_comments(request: Request):
    loop = asyncio.get_event_loop()
    table_comments = await loop.run_in_executor(executor, get_table_comments_dict, engine, None)
    processed_data = {
        "ans": table_comments,
        "type": "success",
        "msg": "表注释获取成功"
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
            "msg": "字段筛选成功"
        }
    else:
        processed_data = {
            "ans": {},
            "type": "error",
            "msg": "字段筛选失败"
        }
    return JSONResponse(content=processed_data)


def _event_stream_filter_db_fields(question: str, tables: Optional[List[str]], session_id: str = "", request_url: str = ""):
    full_content = ""
    prompt_length = 0
    for event in filter_db_fields_stream(question, engine, llm, tables):
        if event.get("type") == "chunk":
            full_content += event.get("content", "")
        if event.get("type") in ("done", "error"):
            prompt_length = event.get("prompt_length", 0)
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    record_session_operation(session_id, request_url, question, ans=full_content, result_type="success", prompt_length=prompt_length)


@app.post("/api/filter-db-fields/stream/")
async def filter_db_fields_stream_api(request: Request, user_input: AgentInput):
    return StreamingResponse(
        _event_stream_filter_db_fields(user_input.question, user_input.tables, user_input.session_id or "", request.url.path),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


def _event_stream_filter_functions(question: str, session_id: str = "", request_url: str = ""):
    full_content = ""
    prompt_length = 0
    for event in filter_functions_stream(question, llm):
        if event.get("type") == "chunk":
            full_content += event.get("content", "")
        if event.get("type") == "done":
            prompt_length = event.get("prompt_length", 0)
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    record_session_operation(session_id, request_url, question, ans=full_content, result_type="success", prompt_length=prompt_length)


@app.post("/api/filter-functions/stream/")
async def filter_functions_stream_api(request: Request, user_input: AgentInput):
    return StreamingResponse(
        _event_stream_filter_functions(user_input.question, user_input.session_id or "", request.url.path),
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
        raise HTTPException(
            status_code=400,
            detail="Only CSV files are supported"
        )
    try:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(executor, process_csv_to_database, content, table_name)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File processing error: {str(e)}")


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


def _event_stream_generate_code(question: str, tables: Optional[List[str]], selected_fields: Optional[Dict[str, Any]] = None, selected_functions: Optional[List[str]] = None, session_id: str = "", request_url: str = ""):
    full_code = ""
    prompt_length = 0
    for event in generate_code_stream(question, tables, True, selected_fields=selected_fields, selected_functions=selected_functions):
        if event.get("type") == "code_complete":
            full_code = event.get("content", "")
        if event.get("type") == "done":
            prompt_length = event.get("prompt_length", 0)
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    record_session_operation(session_id, request_url, question, code=full_code, result_type="success", prompt_length=prompt_length)


def _event_stream_execute_code(code: str, session_id: str = "", request_url: str = ""):
    full_ans = ""
    exec_error = None
    for event in execute_code_stream(code):
        if event.get("type") == "chunk":
            full_ans += event.get("content", "")
        elif event.get("type") == "error":
            exec_error = event.get("content", "")
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    if exec_error:
        record_session_operation(session_id, request_url, "", ans=full_ans, code=code, result_type="error", msg=exec_error[:500], prompt_length=len(code))
    else:
        record_session_operation(session_id, request_url, "", ans=full_ans, code=code, result_type="success", prompt_length=len(code))


def _event_stream_generate_and_execute(question: str, tables: Optional[List[str]], selected_fields: Optional[Dict[str, Any]] = None, selected_functions: Optional[List[str]] = None, session_id: str = "", request_url: str = ""):
    full_code = ""
    full_ans = ""
    exec_error = None
    prompt_length = 0
    for event in generate_and_execute_stream(question, tables, True, selected_fields=selected_fields, selected_functions=selected_functions):
        if event.get("type") == "code_complete" and event.get("phase") == "code":
            full_code = event.get("content", "")
        if event.get("type") == "done" and event.get("phase") == "exec":
            prompt_length = event.get("prompt_length", 0)
        if event.get("type") == "chunk" and event.get("phase") == "exec":
            full_ans += event.get("content", "")
        if event.get("type") == "error" and event.get("phase") == "exec":
            exec_error = event.get("content", "")
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    if exec_error:
        record_session_operation(session_id, request_url, question, ans=full_ans, code=full_code, result_type="error", msg=exec_error[:500], prompt_length=prompt_length)
    else:
        record_session_operation(session_id, request_url, question, ans=full_ans, code=full_code, result_type="success", prompt_length=prompt_length)


def _event_stream_step_chat(question: str, tables=None, selected_fields=None, session_id: str = "", request_url: str = ""):
    full_content = ""
    prompt_length = 0
    for chunk in get_step_chat_stream(question, tables, selected_fields):
        if isinstance(chunk, dict) and "prompt_length" in chunk:
            prompt_length = chunk["prompt_length"]
            continue
        full_content += chunk
        yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'type': 'done', 'content': ''}, ensure_ascii=False)}\n\n"
    record_session_operation(session_id, request_url, question, ans=full_content, result_type="success", prompt_length=prompt_length)


class CodeInput(BaseModel):
    code: str
    session_id: Optional[str] = None


@app.post("/api/generate-code/stream/")
async def generate_code_stream_api(request: Request, user_input: AgentInput):
    return StreamingResponse(
        _event_stream_generate_code(user_input.question, user_input.tables, user_input.selected_fields, user_input.selected_functions, user_input.session_id or "", request.url.path),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.post("/api/exe-code/stream/")
async def execute_code_stream_api(request: Request, code_input: CodeInput):
    return StreamingResponse(
        _event_stream_execute_code(code_input.code, code_input.session_id or "", request.url.path),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.post("/api/generate-and-execute/stream/")
async def generate_and_execute_stream_api(request: Request, user_input: AgentInput):
    return StreamingResponse(
        _event_stream_generate_and_execute(user_input.question, user_input.tables, user_input.selected_fields, user_input.selected_functions, user_input.session_id or "", request.url.path),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.post("/api/step-chat/stream/")
async def step_chat_stream(request: Request, user_input: AgentInput):
    return StreamingResponse(
        _event_stream_step_chat(user_input.question, user_input.tables, user_input.selected_fields, user_input.session_id or "", request.url.path),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.post("/api/plain-chat/")
async def plain_chat(request: Request, user_input: AgentInput):
    loop = asyncio.get_event_loop()
    ans = await loop.run_in_executor(executor, get_plain_chat, user_input.question, user_input.tables, user_input.selected_fields)
    print(ans)
    if ans:
        processed_data = {
            "question": user_input.question,
            "ans": ans,
            "type": "success",
            "msg": "处理成功",
            "session_id": user_input.session_id or ""
        }
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.question, ans, "", "success", "处理成功"
        )
    else:
        processed_data = {
            "question": user_input.question,
            "ans": "",
            "type": "error",
            "msg": "处理失败，请换个问法吧",
            "session_id": user_input.session_id or ""
        }
        record_session_operation(
            user_input.session_id, request.url.path,
            user_input.question, "", "", "error", "处理失败，请换个问法吧"
        )
    return JSONResponse(content=processed_data)


def _event_stream_plain_chat(question: str, tables=None, selected_fields=None, session_id: str = "", request_url: str = ""):
    full_content = ""
    prompt_length = 0
    for chunk in get_plain_chat_stream(question, tables, selected_fields):
        if isinstance(chunk, dict) and "prompt_length" in chunk:
            prompt_length = chunk["prompt_length"]
            continue
        full_content += chunk
        yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'type': 'done', 'content': ''}, ensure_ascii=False)}\n\n"
    record_session_operation(session_id, request_url, question, ans=full_content, result_type="success", prompt_length=prompt_length)


@app.post("/api/plain-chat/stream/")
async def plain_chat_stream(request: Request, user_input: AgentInput):
    return StreamingResponse(
        _event_stream_plain_chat(user_input.question, user_input.tables, user_input.selected_fields, user_input.session_id or "", request.url.path),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


from agent.think import router as think_router
from agent.act import router as act_router
from agent.observe import router as observe_router

app.include_router(think_router)
app.include_router(act_router)
app.include_router(observe_router)


if __name__ == "__main__":
    try:
        uvicorn.run(app, host=config_data['server_host'], port=config_data['server_port'])
    finally:
        executor.shutdown(wait=True)