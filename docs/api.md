# Data Copilot API 文档

Base URL: `http://<host>:8008`

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

返回功能开关配置。

**响应** `200`
```json
{
  "enable_mcp": true,
  "enable_base_knowledge": true,
  "enable_web_search": true,
  "enable_fetch_url": true,
  "enable_target_knowledge": false
}
```

### GET `/api/tools/functions`

列出所有内置 Python 函数（供 Agent 调用）。

**响应** `200`
```json
[
  {
    "name": "query_database",
    "description": "使用自然语言查询数据库",
    "doc": "query_database(question: str, ...)"
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

**错误** `404`: 表不存在。

### GET `/api/table/{table_name}/export-data-csv`

导出表数据为 CSV 文件。

**参数**: `table_name` (路径)

**响应** `200` — `text/csv` 文件下载。

### GET `/{static_folder}/{filename}`

获取静态文件（图片、CSV 等）。

**参数**: `filename` (路径), `download` (可选查询参数)

**查询参数**:
- `download=1` — 强制浏览器下载

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

获取会话的完整对话历史。

**参数**: `session_id` (路径)

**响应** `200`
```json
{ "messages": [...], "actions": [...] }
```

**错误** `404`: 会话不存在。

### GET `/api/session/{session_id}/generated-files`

列出会话生成的报告文件。

**参数**: `session_id` (路径)

**响应** `200`
```json
{ "files": ["report_xxx.md", "report_xxx.docx"] }
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

### POST `/api/think/stream/`

**请求体 — `ThinkInput`**
```json
{
  "question": "分析上个月销售趋势",
  "session_id": "xxx",
  "conversation_history": [...]
}
```

**事件**: `chunk` (type: chunk, phase: think)

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

**事件**: `chunk` (JSON 动作描述)

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

**`action` 可选值**: `explore_schema`, `explore_functions`, `explore_base_knowledge`, `generate_and_execute`, `generate_document`, `web_search`, `fetch_webpage`, `explore_mcp`, `exe_mcp`

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

**事件**: `chunk` (type: chunk, phase: observe)

---

### POST `/api/generate-and-execute/stream/`

一步生成并执行代码（跳过 Think/Action/Observe 流程）。

**请求体 — `AgentInput`**
```json
{
  "question": "计算每个月的总销售额",
  "tables": ["orders"],
  "selected_fields": {"orders": ["amount", "date"]},
  "selected_functions": ["query_database"],
  "session_id": "xxx"
}
```

**事件**:
```
data: {"type":"chunk","sub_type":"code_chunk","phase":"generate","content":"..."}
data: {"type":"chunk","sub_type":"exec_chunk","phase":"exec","content":"..."}
data: {"type":"done","sub_type":"","phase":"done","content":"...","ans":"..."}
data: {"type":"chunk","sub_type":"code_gen_error","phase":"exec","content":"error msg"}
```

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

**事件**: `chunk`, `done`, `error`

### POST `/api/filter-functions/stream/`

使用 LLM 筛选相关的 Python 函数。

**请求体 — `AgentInput`**

**事件**: `chunk`, `done`, `error`

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
  "session_id": "xxx"
}
```

### POST `/api/get-graph/`

基于数据生成图表。

**请求体**
```json
{
  "question": "画柱状图展示每月销售额",
  "data": {"month": ["1月","2月"], "sales": [100, 200]},
  "session_id": "xxx"
}
```

**响应** `200`
```json
{
  "question": "画柱状图展示每月销售额",
  "ans": "/tmp_imgs/chart_abc123.png",
  "type": "success"
}
```

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

**事件**:
```
data: {"type":"chunk","phase":"outline","content":"..."}
data: {"type":"chunk","phase":"writing","content":"..."}
data: {"type":"chunk","phase":"done","file_name":"report_xxx"}
```

### POST `/api/generate-document/stream/unified/`

单次通过的文档生成（统一提示）。

**请求体 — `DocumentInput`**

**事件**: 同上。

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
{ "prompt": "你是一位数据分析师...", "sections": [...] }
```

### POST `/api/generate-document/stream/from-yaml/`

从 YAML 大纲生成文档内容。

**请求体 — `YamlDocumentInput`**
```json
{
  "conversation_history": [...],
  "yaml_outline": {...},
  "session_id": "xxx",
  "section_index": null,
  "confirmed_sections": [],
  "yaml_base": "outline_xxx"
}
```

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

列出 `doc_workspace/` 目录下的 YAML 文件。

**响应** `200`
```json
{ "files": ["outline_xxx.yaml"] }
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

**响应** `200`
```json
[
  {
    "id": 1,
    "key": "数据库命名规范",
    "value": "表名使用小写蛇形命名",
    "created_at": "...",
    "updated_at": "..."
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

**响应** `201` — 创建后的记录。

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

`attr` 不存在时自动创建。

**响应** `200`
```json
{ "attr": "database_type", "value": "PostgreSQL" }
```

---

## 8. 文件上传

### POST `/upload-csv/`

上传 CSV 文件并插入数据库。

**请求体** — `multipart/form-data`

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `file` | File | — | CSV 文件 |
| `table_name` | Form | `"uploaded_data"` | 目标表名 |

**响应** `200`
```json
{
  "status": "success",
  "table_name": "uploaded_data",
  "rows_inserted": 100
}
```

### POST `/upload-txt/`

上传文档文件（TXT/DOC/DOCX/PDF），提取内容并用 LLM 生成数据注释。

**请求体** — `multipart/form-data`

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `file` | File | — | 支持 `.txt`, `.doc`, `.docx`, `.pdf` |
| `table_name` | Form | `"uploaded_data"` | 目标表名 |

**响应** `200`
```json
{
  "status": "success",
  "table_name": "uploaded_data",
  "extracted_text_length": 2500,
  "preview": "提取的内容前500字..."
}
```

---

## 注释管理

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
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 409 | 资源冲突（如键已存在）|
| 500 | 服务器内部错误 |
| 502 | 代理连接后端失败（仅 front.py） |