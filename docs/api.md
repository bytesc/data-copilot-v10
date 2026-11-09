# Data Copilot API 文档

Base URL: `http://<host>:8008`

> **统一请求信封（可选）**：JSON `POST/PUT/PATCH` 可以发送
> `{"meta": {"model": "...", "reasoning_effort": "...", "style": "...", "use_images": true}, "data": {...}}`。
> 下文请求体示例若无特别说明，展示的是 `data` 内容。信封为可选：中间件仅在请求同时携带 `meta` 与 `data` 时自动解包（`meta` 用于本次 LLM 调用，`data` 作为转发给接口的新请求体）；未携带信封的普通 JSON 主体原样透传，不会返回 `400`。
> 模型选项（`model`/`reasoning_effort`/`style`/`use_images`）只能经信封（JSON）或 Multipart 的 `meta` 表单字段传入，后者目前仅 `/upload-txt/` 会读取。
> `reasoning_effort` / `style` 为空字符串表示 `Default`。`use_images` 控制是否随请求上传 blackboard 图片，仅对 `supports_images=true` 的模型生效；未携带时按模型能力取默认值。后端不保存选择，GET/DELETE 不使用信封。
> **用户上传图片**不走 Multipart、也没有独立接口：前端把图片以 base64 放进 `data.conversation_history` 的 user 条目的 `uploaded` 字段（`[{"name": "a.png", "data": "data:image/png;base64,..."}]`）。后端信封中间件会解码保存为 `tmp_imgs/upload_<8位小写字母>.png`，把 `uploaded` 改写为文件名列表，并追加合并进 blackboard 的 `selected_images` 区域。详见 [4. Agent 核心流程](#4-agent-核心流程-sse-流式) 的「用户上传图片」小节。

---

## 目录

- [配置与元数据](#1-配置与元数据)
- [数据库管理](#2-数据库管理)
- [会话与日志](#3-会话与日志)
- [Agent 核心流程 (SSE 流式)](#4-agent-核心流程-sse-流式)
- [图表与工具](#5-图表与工具)
- [文档生成](#6-文档生成)
- [系统知识管理 (CRUD)](#7-系统知识管理-crud)
- [文件上传](#8-文件上传)

---

## 1. 配置与元数据

### GET `/api/config`

返回功能开关配置与模型列表。

**响应** `200`
```json
{
  "enable_mcp": true,
  "enable_base_knowledge": true,
  "enable_web_search": true,
  "enable_fetch_url": true,
  "enable_target_knowledge": false,
  "enable_edit": true,
  "models": [
    {
      "id": "deepseek-v4.1-flash",
      "name": "DeepSeek V4.1 Flash",
      "model": "deepseek-v4.1-flash",
      "url": "https://tokenhub.tencentmaas.com/v1",
      "reasoning_effort_options": ["none", "low", "high", "max"],
      "reasoning_effort_selected": "none",
      "style_options": ["Formal", "Casual", "Technical"],
      "style_selected": "",
      "supports_images": true
    },
    {
      "id": "deepseek-v4-flash",
      "name": "DeepSeek V4 Flash",
      "model": "deepseek-v4-flash",
      "url": "https://tokenhub.tencentmaas.com/v1",
      "reasoning_effort_options": ["none", "low", "high", "max"],
      "reasoning_effort_selected": "",
      "style_options": ["Formal", "Casual", "Technical"],
      "style_selected": "",
      "supports_images": false
    }
  ],
  "current_model": "deepseek-v4.1-flash",
  "current_reasoning_effort": "none",
  "current_style": ""
}
```

> **`models`** 按 `config/config.yaml` 的 `llm_models` 全量返回（上例仅列出前两个，实际还包含 `glm-5.3-flash`、`glm-5.3-flashx`）；默认（第一个）模型为 `deepseek-v4.1-flash`。

> **`enable_edit`**: 设为 `false` 时，数据管理（`/api/db-overview/`、删表、数据/注释导出、注释编辑、上传）与系统知识管理（`/api/sys-knowledge/*`）等接口全部返回 `403`；前端同时隐藏 Data、Knowledge 页面并拦截其路由。

> GET 请求没有 `meta`，因此 `current_*` 返回默认值（第一个模型、Depth 第一个值、Style `Default`）。前端用 localStorage 的 `data-copilot-llm-config` 缓存模型配置列表和选择；启动时从后端获取并校验，不一致或选择失效时回退默认值。

> **`models`**: 配置的模型列表及 Depth/Style 可选值，前端据此渲染下拉框；对应配置缺失时下拉禁用。
> **`supports_images`**: 模型是否支持图片多模态输入。前端据此渲染 Images 开关：支持时默认开启，不支持时关闭并置灰；实际提交还受请求 `meta.use_images` 控制。

### GET `/api/models/`

返回配置的模型列表与默认选择。

**响应** `200` — 结构同 `/api/config` 中的 `models`、`current_model`、`current_reasoning_effort`、`current_style`。

模型/Depth/Style 选择完全由前端本地保存与校验（localStorage `data-copilot-llm-config`），后端仅提供只读的 `GET /api/config` 与 `GET /api/models/`，不存在对应的 POST 选择端点。

### GET `/api/tools/functions`

列出所有内置 Python 函数（供 Agent 调用）。

**响应** `200`
```json
[
  {
    "name": "exe_sql",
    "description": "执行 SQL 查询字符串，返回 pandas DataFrame",
    "doc": "exe_sql(sql: str) -> pd.DataFrame"
  }
]
```

### GET `/api/tools/custom-functions`

列出用户注册的自定义 Python 函数。

**响应** `200` — 同上格式。

### GET `/api/tools/mcp`

列出所有配置的 MCP 服务器及其工具（超时 35s）。

**响应** `200`
```json
[
  {
    "server_name": "calculator",
    "server_description": "",
    "url": "http://localhost:8101/sse",
    "tools": [
      { "name": "add", "description": "Add two numbers", "parameters": ["a","b"] }
    ],
    "error": null
  }
]
```

---

## 2. 数据库管理

> 以下接口受 `enable_edit` 控制。设为 `false` 时返回 `403`（`{ "detail": "Editing is disabled by configuration" }`）：
> `GET /api/db-overview/`、`DELETE /api/table/{table_name}`、`GET /api/table/{table_name}/export-data-csv`，以及"注释管理"一节的全部接口（查看、导入、导出、编辑）。

### GET `/api/db-overview/`

获取所有数据库表的概览（表名、注释、列、前 5 行样例数据）。

**响应** `200`
```json
{
  "tables": [
    {
      "name": "users",
      "comment": "用户表",
      "columns": [{"name": "id", "comment": "主键"}],
      "rows": [{"id": "1", "name": "Alice"}]
    }
  ]
}
```

### GET `/api/table-names/`

获取所有表名列表。

**响应** `200`
```json
{ "tables": ["users", "orders"] }
```

### DELETE `/api/table/{table_name}`

删除指定表。

**参数**: `table_name` (路径)

**响应** `200`
```json
{ "deleted": true, "table": "users" }
```

**错误** `404`: 表不存在。`403`: `enable_edit=false`。

### GET `/api/table/{table_name}/export-data-csv`

导出表数据为 CSV 文件。

**参数**: `table_name` (路径)

**响应** `200` — `text/csv` 文件下载。

**错误** `403`: `enable_edit=false`。

### GET `/tmp_imgs/{filename}`

获取静态文件（图片、CSV 等）。目录固定为项目根目录下的 `tmp_imgs/`。

**参数**: `filename` (路径), `download` (可选查询参数)

**查询参数**:
- `download` — 只要请求携带该参数（无论取值，如 `download=1`、`download=`），即强制浏览器下载（`Content-Disposition: attachment`）；不携带则在线展示

**响应** `200` — 文件内容。

---

## 3. 会话与日志

### GET `/api/sessions/?limit=50`

列出最近会话。

**查询参数**: `limit` (int, 默认 50)

**响应** `200`
```json
{ "sessions": [{ "session_id": "xxx", ... }] }
```

### GET `/api/session/{session_id}/history`

获取会话的完整对话历史。直接返回 `data_access/observe_log.py` 的 `reconstruct_conversation_history(session_id)` 结果。

**参数**: `session_id` (路径)

**响应** `200`
```json
{
  "session_id": "xxx",
  "question": "查询上个月销售额",
  "status": "active",
  "total_cycles": 3,
  "total_tokens": 12000,
  "created_at": "2026-01-01 10:00:00",
  "updated_at": "2026-01-01 10:05:00",
  "conversation_history": [...],
  "cycle_count": 3
}
```

**错误** `404`: 会话不存在（`{"error": "Session not found"}`）。

### GET `/api/session/{session_id}/generated-files`

列出会话生成的报告文件（来自 `data_access/report_log.py` 的 `get_generated_files`，每项为对象而非文件名字符串）。

**参数**: `session_id` (路径)

**响应** `200`
```json
{
  "files": [
    {
      "id": 1,
      "title": "销售分析报告",
      "downloadUrlMd": "http://127.0.0.1:8008/tmp_imgs/doc_xxxx.md",
      "downloadUrlDocx": "http://127.0.0.1:8008/tmp_imgs/doc_xxxx.docx",
      "downloadUrlPdf": "http://127.0.0.1:8008/tmp_imgs/doc_xxxx.pdf",
      "createdAt": "2026-01-01T10:05:00"
    }
  ]
}
```

### POST `/api/log-user-input/`

记录用户输入到观察日志。

**请求体**
```json
{
  "session_id": "xxx",
  "cycle_index": 0,
  "user_input": "查询上个月销售额"
}
```

**响应** `200`
```json
{ "status": "ok" }
```

---

## 4. Agent 核心流程 (SSE 流式)

所有流式接口使用 `text/event-stream`，格式为 `data: {json}\n\n`。

| 阶段 | 端点 | 说明 |
|------|------|------|
| **Think** | `POST /api/think/stream/` | LLM 生成结构化计划 |
| **Action** | `POST /api/action/stream/` | LLM 决定下一步操作 |
| **Act** | `POST /api/act/stream/` | 执行指定操作 |
| **Observe** | `POST /api/observe/stream/` | LLM 审查结果并更新计划 |

### 通用事件格式

```
data: {"type":"chunk","sub_type":"code_chunk","content":"..."}
data: {"type":"chunk","sub_type":"exec_chunk","content":"..."}
data: {"type":"chunk","content":"...","phase":"think"}
data: {"type":"error","content":"..."}
data: {"type":"done","content":""}
```

> **Think / Action / Observe 三个流的完整事件集**：除 `chunk` 外，还会发出 `msg`（阶段提示）、`reasoning_chunk`、终态 `done`（Think/Observe 附带 `plan_result`，Action 附带 `action_result`）、收尾的 `history` 事件（携带保存后的会话历史），以及失败时的 `error`（Observe 流内部异常时额外带 `fatal: true`）。各事件的字段与顺序详见 `docs/sse_event_flow.md`。

### POST `/api/think/stream/`

**请求体 — `ThinkInput`**
```json
{
  "question": "分析上个月销售趋势",
  "session_id": "xxx",
  "conversation_history": [...]
}
```

**事件**: `msg`、`chunk` (phase: think)、`reasoning_chunk`、`done`（含 `plan_result`）、`history`、`error`

### POST `/api/action/stream/`

**请求体 — `ActionInput`**
```json
{
  "question": "分析上个月销售趋势",
  "session_id": "xxx",
  "conversation_history": [...],
  "cycle_index": 0
}
```

**事件**: `msg`、`chunk` (JSON 动作描述)、`reasoning_chunk`、`done`（含 `action_result`）、`history`、`error`

### POST `/api/act/stream/`

**请求体 — `ActInput`**
```json
{
  "question": "分析上个月销售趋势",
  "action": "explore_schema",
  "session_id": "xxx",
  "conversation_history": [...],
  "params": {}
}
```

**`action` 可选值**（`agent/action.py` 的 `VALID_ACTIONS`）: `explore_schema`, `explore_functions`, `generate_and_execute`, `ask_question`, `ask_choice`, `summary_and_pause`, `attempt_completion`, `generate_document`, `select_images`；以及按配置开关追加的 `explore_base_knowledge`（`enable_base_knowledge`）、`web_search`（`enable_web_search`）、`fetch_webpage`（`enable_fetch_url`）、`explore_mcp` / `exe_mcp`（`enable_mcp`）。

`select_images` 的 `params` 形如 `{"images": [{"path": "xxx.png", "reason": "一句话选中原因"}]}`；`path` 为本地 `tmp_imgs` 文件名或完整 `http(s)` 链接，整体覆盖 blackboard 的 `selected_images` 区域，`images: []` 表示清空。用户上传的图片会**追加合并**进同一区域（不通过本 action），见「用户上传图片」小节。

**事件**: `code_chunk`, `exec_chunk`, `code_gen_error`

### POST `/api/observe/stream/`

**请求体 — `ObserveInput`**
```json
{
  "question": "分析上个月销售趋势",
  "session_id": "xxx",
  "conversation_history": [...],
  "cycle_index": 1
}
```

**事件**: `status`、`msg`、`chunk` (phase: observe)、`reasoning_chunk`、`done`（含 `plan_result`）、`history`、`error`（流崩溃时附带 `fatal: true`）

---

### 用户上传图片

图片随任意携带 `conversation_history` 的 JSON 请求一起提交（通常是本轮第一个请求：Think 模式为 `POST /api/think/stream/`，Chat 模式为 `POST /api/action/stream/`），**没有独立的上传接口，也不走 Multipart**。前端在浏览器内暂存图片，点击发送时才编码为 base64。

**请求体中 user 条目带 `uploaded`**（在 `data.conversation_history` 内）：

```json
{
  "meta": {"model": "deepseek-v4.1-flash", "use_images": true},
  "data": {
    "question": "分析这些图片",
    "session_id": "xxx",
    "conversation_history": [
      {"role":"user","type":"question","content":"分析这些图片","uploaded":[
        {"name":"cat.jpg","data":"data:image/jpeg;base64,..."}
      ]}
    ]
  }
}
```

**后端处理**（`main.py` 的 `unified_request_envelope` → `utils/image_ingest.py` 的 `ingest_uploaded_images`）：

1. 解码每个 base64 项并保存为 `tmp_imgs/upload_<8位小写字母>.png`（扩展名与生成图片一致，非 `RGB`/`RGBA` 会转换；单张 ≤20MB）。
2. 把该条目的 `uploaded` 改写为文件名列表 `["upload_abcd1234.png"]`。
3. 把这些文件名追加合并进 blackboard 的 `selected_images` 区域（每项 `{"path", "reason": "user uploaded image"}`，按 `path` 去重，不覆盖已有选中项）。

处理发生在路由之前且**幂等**：后续阶段收到的 `conversation_history` 里 `uploaded` 已是文件名，不会再解码或重复合并；当前请求构建的 `## Context` 已能看到 `Uploaded images: ...` 文件名列表。文件名随会话历史持久化；若 `meta.use_images` 开启且模型 `supports_images=true`，图片会按 `selected_images` 规则作为 `image_url` 提交。

> 前端卡控最多 10 张；后端同样有硬性上限（`utils/image_ingest.py`）：单请求最多解码/保存 10 张（`MAX_IMAGES_PER_REQUEST`），总字节上限 50 MB（`MAX_TOTAL_IMAGE_BYTES`，按 base64 长度保守估算）。超限的图片会被静默丢弃（原始 base64 同时从历史中剔除），图片保存失败或为空也会被跳过，均不影响其余消息。

---

### POST `/api/generate-and-execute/stream/`

一步生成并执行代码（跳过 Think/Action/Observe 流程）。

**请求体 — `AgentInput`**
```json
{
  "question": "计算每个月的总销售额",
  "tables": ["orders"],
  "selected_fields": {"orders": ["amount", "date"]},
  "selected_functions": ["exe_sql"],
  "session_id": "xxx"
}
```

**事件**（`agent/agent.py` 的 `generate_and_execute_stream`，`phase` 恒为 `"act"`）:
```
data: {"type":"msg","content":"Analyzing question...","phase":"act","sub_phase":"code"}
data: {"type":"msg","content":"Generating code...","phase":"act","sub_phase":"code"}
data: {"type":"chunk","sub_type":"code_chunk","content":"...","phase":"act","sub_phase":"code"}
data: {"type":"reasoning_chunk","content":"...","phase":"act","sub_phase":"code"}
data: {"type":"chunk","sub_type":"code_complete","content":"def ...","phase":"act","sub_phase":"code"}
data: {"type":"chunk","sub_type":"code_gen_error","content":"code generation error","phase":"act","sub_phase":"code"}
data: {"type":"msg","content":"Executing code...","phase":"act","sub_phase":"exec"}
data: {"type":"chunk","sub_type":"exec_chunk","content":"...","phase":"act","sub_phase":"exec"}
data: {"type":"chunk","sub_type":"code_exe_error","content":"...","phase":"act","sub_phase":"exec"}
data: {"type":"chunk","sub_type":"exec_complete","content":"...","phase":"act","sub_phase":"exec","images":["xxx.png"]}
data: {"type":"done","code":"...","content":"...","phase":"act","sub_phase":"exec","images":["xxx.png"]}
data: {"type":"error","content":"generate_and_execute_stream_error","phase":"act"}
```

> 终态成功事件为 `done`（含 `code` / `content` / `images`，**没有** `ans` 字段）；`code_gen_error` 的 `phase` 为 `"act"`；重试耗尽时发出 `{"type":"error","content":"generate_and_execute_stream_error","phase":"act"}`。

### POST `/api/plain-chat/stream/`

纯 LLM 聊天，无需 Agent 管道步骤。

**请求体 — `AgentInput`**

**事件**:
```
data: {"type":"chunk","content":"..."}
data: {"type":"done","content":""}
```

### POST `/api/filter-db-fields/stream/`

使用 LLM 筛选与问题相关的数据库字段。

**请求体 — `AgentInput`**

**事件**: `status`, `chunk`, `done`, `error`（先发若干 `status`，再流式 `chunk`，最后要么 `done` 要么 `error`）

### POST `/api/filter-functions/stream/`

使用 LLM 筛选相关的 Python 函数。

**请求体 — `AgentInput`**

**事件**: `status`, `chunk`, `done`（先发 `status`，再流式 `chunk`，最后 `done`；不会发出 `error` 事件）

---

## 5. 图表与工具

### POST `/api/exe-sql/`

直接执行 SQL 查询。

**请求体**
```json
{
  "question": "SELECT * FROM orders LIMIT 5",
  "session_id": "xxx"
}
```

**响应** `200`
```json
{
  "ans": [{"id": 1, "amount": 100}],
  "type": "success",
  "msg": "处理成功",
  "session_id": "xxx"
}
```

**错误** `503`: 未配置只读数据库（`mysql_readonly` 缺失/为空）时返回 `{"detail": "No read-only database is configured (mysql_readonly is missing)"}`——只读查询被禁用，不会回退到特权账号。

### POST `/api/db-slice/`

获取所有表的前 5 行数据。

**响应** `200`
```json
{
  "ans": {
    "orders": {
      "columns": ["id", "amount"],
      "data": [[1, 100], [2, 200]]
    }
  }
}
```

### POST `/api/db-comments/`

获取所有表和列注释。

**响应** `200`
```json
{
  "ans": {
    "orders": {
      "table_comment": "订单表",
      "columns": {"id": "主键", "amount": "金额"}
    }
  }
}
```

### POST `/api/table-comments/`

获取所有表的表注释（不含列注释）。

**响应** `200`
```json
{
  "ans": {"orders": "订单表", "users": ""},
  "type": "success",
  "msg": "Table comments fetched successfully"
}
```

### POST `/api/filter-db-fields/` (非流式)

与流式版本相同，但返回完整响应而非 SSE。

---

## 6. 文档生成

### POST `/api/generate-document/stream/`

多步文档生成：生成大纲 → 逐部分编写 → 保存 MD/DOCX/PDF。

**请求体 — `DocumentInput`**
```json
{
  "conversation_history": [...],
  "session_id": "xxx"
}
```

**事件**（`agent/document_generator.py` 的 `_event_stream_generate_document`）:
```
data: {"phase":"outline","type":"msg","content":"Generating document outline..."}
data: {"phase":"outline","type":"chunk","content":"..."}
data: {"phase":"outline","type":"done","content":"...","outline":{"title":"...","parts":[{"heading":"...","description":"..."}]}}
data: {"phase":"part","type":"msg","content":"Generating part 1/N: ...","part_index":0,"heading":"..."}
data: {"phase":"part","type":"chunk","content":"...","part_index":0}
data: {"phase":"part","type":"done","content":"...","part_index":0,"heading":"..."}
data: {"phase":"document","type":"done","content":"...","title":"...","parts_count":N,"file_name":"doc_xxxx","download_url_md":"...","download_url_docx":"...","download_url_pdf":"...","conversation_history":[...]}
```

> 阶段依次为 `outline` → `part`（每个部分一次 msg/chunk/done），终态 `done` 事件的 `phase` 为 `"document"`。大纲无 parts 时发出 `{"phase":"outline","type":"error","content":"No parts generated in outline"}`。

### POST `/api/generate-document/stream/unified/`

单次通过的文档生成（统一提示）。走 `agent/act.py` 的 `generate_document` action 路径，事件带 `phase:"act"` 与 `sub_phase:"generate_document"`。

**请求体 — `DocumentInput`**

**事件**（`_event_stream_generate_document_unified`）:
```
data: {"phase":"act","sub_phase":"generate_document","type":"msg","content":"Generating document..."}
data: {"phase":"act","sub_phase":"generate_document","type":"chunk","content":"..."}
data: {"phase":"act","sub_phase":"generate_document","type":"done","content":"..."}
data: {"phase":"act","sub_phase":"generate_document","type":"done","content":"<full markdown>","title":"...","file_name":"doc_xxxx","download_url_md":"...","download_url_docx":"...","download_url_pdf":"...","conversation_history":[...]}
```

> 统一模式会先发一个仅含 `content` 的 `done`，再发一个含完整文件元数据的 `done`。

### POST `/api/generate-document/generate-yaml-outline/`

从对话历史生成 YAML 格式的文档大纲。

**请求体 — `YamlOutlineInput`**
```json
{
  "conversation_history": [...],
  "session_id": "xxx",
  "user_prompt": "生成一份关于销售分析的报告"
}
```

### POST `/api/generate-document/yaml-to-prompt/`

将 YAML 大纲转换为聊天提示（纯格式化，不调用 LLM）。

**请求体**
```json
{ "yaml_content": "sections:\n  - title: 概述\n    prompt: ..." }
```

**响应** `200`
```json
{ "prompt": "The following document outline is a YAML template. ..." }
```

**错误** `400` — `yaml_content` 为空/缺失时返回 `{"error": "yaml_content is required"}`。

### POST `/api/generate-document/stream/from-yaml/`

从 YAML 大纲生成文档内容。

**请求体 — `YamlDocumentInput`**
```json
{
  "conversation_history": [...],
  "yaml_outline": "title: 销售分析报告\nsections:\n  - heading: 概述\n    description: 报告背景与分析目标",
  "session_id": "xxx",
  "section_index": null,
  "confirmed_sections": [],
  "yaml_base": "outline_xxx"
}
```

> `yaml_outline` 为**必填的 YAML 字符串**（`YamlDocumentInput` 中声明为 `str`）；传 JSON 对象会因校验失败返回 `422`。

`section_index` 为 `null` 时生成全部内容。

### POST `/api/generate-document/finalize/`

将编辑后的 Markdown 转换为 MD/DOCX/PDF。

**请求体 — `FinalizeInput`**
```json
{
  "markdown_content": "# 报告\n...",
  "session_id": "xxx",
  "yaml_base": "outline_xxx",
  "conversation_history": [...]
}
```

### 文档工作区

#### GET `/api/doc-workspace/files/`

列出 `doc_workspace/` 目录下的 YAML 文件（每项为对象，按文件名倒序）。

**响应** `200`
```json
{ "files": [{"name": "outline_xxx.yaml", "type": "yaml", "mtime": 1735700000.0}] }
```

#### GET `/api/doc-workspace/file/{filename}`

读取工作区文件内容。`filename` 禁止包含 `../` 或 `/`。

#### POST `/api/doc-workspace/save/{filename}`

保存/覆盖工作区文件。

**请求体**
```json
{ "content": "文件内容..." }
```

#### DELETE `/api/doc-workspace/outline/{filename}`

删除 YAML 大纲文件。`filename` 必须以 `.yaml` 结尾。

#### DELETE `/api/doc-workspace/drafts/{session_id}/{yaml_id}`

删除匹配 `draft_{session_id}_{yaml_id}*.md` 的草稿文件。

---

## 7. 系统知识管理 (CRUD)

> 该节全部接口受 `enable_edit` 控制，设为 `false` 时返回 `403`（`/api/sys-knowledge/*` 路由级拦截）。

通用 CRUD 模式，适用于以下资源：

| 资源 | 端点前缀 | 说明 |
|------|----------|------|
| 基础知识 | `/api/sys-knowledge/base-knowledge/` | 领域基础知识库 |
| DB 查询指南 | `/api/sys-knowledge/db-query-guide/` | SQL 查询最佳实践 |
| 代码指南 | `/api/sys-knowledge/code-guide/` | 代码生成规则 |
| 图表代码指南 | `/api/sys-knowledge/graph-code-guide/` | 图表绘制规则 |
| 思考指南 | `/api/sys-knowledge/think-guide/` | 思考策略 |
| 文档指南 | `/api/sys-knowledge/doc-guide/` | 文档生成规则 |

每个资源 5 个操作：

### LIST — `GET /api/sys-knowledge/{resource}/`

**响应** `200`（仅返回 `id` / `key` / `value`，不含时间戳）
```json
[
  {
    "id": 1,
    "key": "数据库命名规范",
    "value": "表名使用小写蛇形命名"
  }
]
```

### GET — `GET /api/sys-knowledge/{resource}/{item_id}`

**参数**: `item_id` (路径, int)

**响应** `200` — 单条记录。

### CREATE — `POST /api/sys-knowledge/{resource}/`

**请求体**
```json
{
  "key": "数据库命名规范",
  "value": "表名使用小写蛇形命名"
}
```

**响应** `200` — 创建后的记录（`{"id": ..., "key": ..., "value": ...}`；FastAPI 默认状态码）。

**错误** `409`: 键已存在。

### UPDATE — `PUT /api/sys-knowledge/{resource}/{item_id}`

**请求体**
```json
{
  "key": "新键名",
  "value": "新值"
}
```

两个字段都是可选的（只更新提供的字段）。

**响应** `200` — 更新后的记录。

**错误** `400`: 两个字段都未提供时返回 `{"detail": "No fields to update"}`。

### DELETE — `DELETE /api/sys-knowledge/{resource}/{item_id}`

**响应** `200`
```json
{ "deleted": true, "id": 1 }
```

### 简讯 Brief Info

#### GET `/api/sys-knowledge/brief-info/`

列出所有系统简讯属性。

**响应** `200`
```json
[{"attr": "database_type", "value": "MySQL"}]
```

#### PUT `/api/sys-knowledge/brief-info/{attr}`

**请求体**
```json
{ "value": "PostgreSQL" }
```

`attr` 不存在时不会创建，返回 `404 {"detail": "Attribute '<attr>' not found"}`（brief-info 不支持新增/删除）。

**响应** `200`
```json
{ "attr": "database_type", "value": "PostgreSQL" }
```

---

## 8. 文件上传

> 本节接口受 `enable_edit` 控制，设为 `false` 时返回 `403`。
> 图片上传不在本节：图片以 base64 随 JSON 请求的 `conversation_history[].uploaded` 提交，见 [4. Agent 核心流程](#4-agent-核心流程-sse-流式) 的「用户上传图片」小节。

### 上传大小限制

各上传接口对上传体积设有硬性上限，超限返回 `413`。上限由后端常量定义（`main.py`）：

| 接口 | 上限 | 常量 |
|------|------|------|
| `POST /upload-csv/` | 50 MB | `MAX_CSV_UPLOAD_BYTES` |
| `POST /upload-txt/` | 20 MB | `MAX_DOC_UPLOAD_BYTES` |
| `POST /api/comment-manage/{table_name}/import-csv` | 5 MB | `MAX_COMMENT_CSV_BYTES` |

执行方式：

1. **入口预检** — 中间件 `limit_multipart_upload_size` 在解析 `multipart/form-data` 之前读取 `Content-Length`，超过三者的最大值（50 MB，`MAX_MULTIPART_BYTES`）直接返回 `413`，避免超大请求体被解析/落盘。
2. **端点读取** — 每个处理函数通过 `_read_upload_limited(file, 上限)` 以 1 MiB 分块读取，累计超过该接口上限立即返回 `413`。因此即使客户端未提供 `Content-Length`（分块传输）也能按接口上限拦截，且不会把整包读入内存。

> `front.py` 反向代理不做大小限制，仅透传请求；限制一律以后端为准。

### POST `/upload-csv/`

上传 CSV 文件并插入数据库。

**请求体** — `multipart/form-data`

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `file` | File | — | CSV 文件 |
| `table_name` | Form | `"uploaded_data"` | 目标表名 |

> `file` 大小上限 **50 MB**，超限返回 `413`（见「上传大小限制」）。

**响应** `200`（成功）
```json
{
  "success": true,
  "message": "Successfully created table 'uploaded_data' and inserted 100 records.",
  "row_count": 100,
  "table_name": "uploaded_data"
}
```

失败分两类：

- **HTTP `400`（请求级校验失败）**：非 `.csv` 文件返回 `{"detail": "Only CSV files are supported"}`；空文件返回 `{"detail": "Uploaded file is empty"}`。
- **HTTP `200` + `success:false`（数据库侧失败）**：行校验错误或导入异常（`data_access/insert_data_from_csv.py`）返回 `success:false` 与 `error`：
```json
{
  "success": false,
  "error": "Validation failed:\n...",
  "row_count": 0,
  "table_name": "uploaded_data"
}
```

### POST `/upload-txt/`

上传文档文件（TXT/DOC/DOCX/PDF），提取内容并用 LLM 生成数据注释。

**请求体** — `multipart/form-data`

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `file` | File | — | 支持 `.txt`, `.doc`, `.docx`, `.pdf` |
| `table_name` | Form | `"uploaded_data"` | 目标表名 |
| `meta` | Form(string) | `null` | 模型调用选择 JSON，如 `{"model":"glm-5.3-flash","reasoning_effort":"max","style":"Casual","use_images":true}` |

> `file` 大小上限 **20 MB**，超限返回 `413`（见「上传大小限制」）。

**响应** `200`
```json
{
  "status": "success",
  "success": true,
  "message": "Comments were generated and applied to table 'uploaded_data'.",
  "table_name": "uploaded_data",
  "comment_applied": true,
  "extracted_text_length": 2500,
  "preview": "提取的内容前500字..."
}
```

> 当模型未返回有效注释 JSON、或注释未能写入目标表（如表不存在）时，接口仍返回 `200`，但 `success` 为 `false`、`status` 为 `"error"`，并在 `error` 字段给出原因。

---

## 注释管理

> 该节全部接口受 `enable_edit` 控制，设为 `false` 时返回 `403`。

### GET `/api/comment-manage/`

获取所有表的注释管理数据（结构、类型、注释）。

**响应** `200`
```json
{
  "tables": [
    {
      "name": "orders",
      "comment": "订单表",
      "columns": [
        {"name": "id", "type": "INT", "nullable": false, "default": null, "comment": "主键"}
      ]
    }
  ]
}
```

### GET `/api/comment-manage/{table_name}/export-csv`

导出表和列注释为 CSV。

### POST `/api/comment-manage/{table_name}/import-csv`

通过 CSV 导入注释。CSV 需包含 `column_name` 和 `comment` 列。

> CSV 大小上限 **5 MB**，超限返回 `413`（见「上传大小限制」）。

### PUT `/api/comment-manage/{table_name}/table-comment`

更新表注释。

**请求体**
```json
{ "comment": "新的表注释" }
```

### PUT `/api/comment-manage/{table_name}/column/{column_name}/comment`

更新列注释。

**请求体**
```json
{ "comment": "新的列注释" }
```

---

## 通用错误响应

```json
{ "error": "Internal server error", "detail": "..." }
```

| 状态码 | 含义 |
|--------|------|
| 400 | 请求参数错误（如 sys-knowledge PUT 未提供任何字段、上传非 CSV/空文件）；缺省 `{meta, data}` 信封**不会**报 400（信封为可选，见文首说明） |
| 403 | 功能被配置禁用（`enable_edit=false` 时数据/知识管理接口） |
| 404 | 资源不存在 |
| 409 | 资源冲突（如键已存在）|
| 413 | 上传文件超过大小上限（见「文件上传」的「上传大小限制」） |
| 500 | 服务器内部错误 |
| 502 | 代理连接后端失败（仅 front.py） |
| 503 | 只读数据库未配置（`mysql_readonly` 缺失时 `/api/exe-sql/`） |