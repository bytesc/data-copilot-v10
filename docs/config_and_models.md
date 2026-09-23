# 配置与模型格式

## 1. 系统配置 `config/config.yaml`

```yaml
# 服务端口与绑定地址
server_port: 8008
server_host: "0.0.0.0"

# 用户业务数据库（用于查询分析）
mysql: "mysql+pymysql://root:123456@localhost:3306/singapore_land_2"

# 系统数据库（会话日志、知识库、操作审计）
mysql_sys: "mysql+pymysql://root:123456@localhost:3306/data_copilot_v10_land_sys"

# 静态文件 URL 前缀（用于 LLM 构造图片/CSV 链接）
static_path: "http://127.0.0.1:8008/"
# 静态文件存储目录（相对于项目根）
static_folder: "tmp_imgs"

# 大模型
model_name: "deepseek-v4-flash"            # 模型名称，LLM 调用时使用
model_url: "https://tokenhub.tencentmaas.com/v1"  # OpenAI 兼容接口地址

# 功能开关
enable_mcp: true              # MCP 外部工具
enable_base_knowledge: true   # 基础知识库检索
enable_web_search: true       # 联网搜索
enable_fetch_url: true        # 网页内容抓取
enable_target_knowledge: false # 目标模板
enable_llmlog: false           # 记录 LLM 调用日志到 llmlog/*.txt
```

**DSN 格式**: `mysql+pymysql://用户名:密码@主机:端口/数据库名`

---

## 2. 前端环境变量 `vue-front/.env`

```env
VITE_SERVER_URL=http://127.0.0.1:8008
VITE_API_BASE=/api
```

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VITE_SERVER_URL` | `http://127.0.0.1:8008` | 后端服务地址，用于文件下载链接和 Vite 开发代理目标 |
| `VITE_API_BASE` | `/api` | API 路径前缀 |

构建时通过 `import.meta.env.VITE_*` 注入前端代码。未设置时各组件使用硬编码回退值。

---

## 3. MCP 服务器配置 `config/mcp_servers.yaml`

```yaml
mcp_servers:
  - name: "calculator"            # 唯一标识，explore_mcp / exe_mcp 通过此名称引用
    description: "数学计算工具"    # 可选，展示给 LLM 的服务器描述
    transport: "sse"              # "sse"（远程 HTTP）或 "stdio"（本地子进程）
    url: "http://localhost:8101/sse"  # SSE 传输必填

  - name: "filesystem"
    description: "文件系统访问"
    transport: "stdio"
    command: "npx"                           # stdio 传输必填
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]  # 可选参数
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 服务器唯一标识 |
| `description` | 否 | 展示给 LLM 的描述文本 |
| `transport` | 是 | `"sse"`（HTTP 端点）或 `"stdio"`（子进程管道）|
| `url` | 仅 `sse` | SSE 端点地址 |
| `command` | 仅 `stdio` | 启动命令 |
| `args` | 否 | 命令参数列表 |

---

## 4. 请求模型（Pydantic Schemas）

### AgentInput — 通用 Agent 请求

```json
{
  "question": "分析上个月销售趋势",
  "tables": ["orders", "products"],
  "selected_fields": {"orders": ["amount", "date"]},
  "selected_functions": ["query_database", "draw_graph"],
  "session_id": "xxx"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `question` | string | 是 | 用户问题 |
| `tables` | string[] | 否 | 限定查询的表 |
| `selected_fields` | object | 否 | 过滤后的字段字典 |
| `selected_functions` | string[] | 否 | 限定的函数列表 |
| `session_id` | string | 否 | 会话 ID |

**用于**: `POST /api/generate-and-execute/stream/`、`POST /api/plain-chat/stream/`、`POST /api/filter-db-fields/stream/`、`POST /api/filter-functions/stream/`、`POST /api/exe-sql/`

### AgentInputDict

```json
{
  "question": "画柱状图展示每月销售额",
  "data": {"month": ["1月","2月"], "sales": [100, 200]},
  "session_id": "xxx"
}
```

**用于**: `POST /api/get-graph/`

### ThinkInput

```json
{
  "question": "分析上个月销售趋势",
  "session_id": "xxx",
  "conversation_history": [
    {"role": "assistant", "type": "think", "content": {...}}
  ]
}
```

**用于**: `POST /api/think/stream/`

### ActInput

```json
{
  "question": "分析上个月销售趋势",
  "action": "explore_schema",
  "session_id": "xxx",
  "conversation_history": [...],
  "params": {"keyword": "sales"}
}
```

`action` 可选值: `explore_schema`, `explore_functions`, `explore_base_knowledge`, `generate_and_execute`, `generate_document`, `web_search`, `fetch_webpage`, `explore_mcp`, `exe_mcp`

**用于**: `POST /api/act/stream/`

### ActionInput

```json
{
  "question": "分析上个月销售趋势",
  "session_id": "xxx",
  "conversation_history": [...],
  "cycle_index": 0
}
```

**用于**: `POST /api/action/stream/`

### ObserveInput

```json
{
  "question": "分析上个月销售趋势",
  "session_id": "xxx",
  "conversation_history": [...],
  "cycle_index": 1
}
```

**用于**: `POST /api/observe/stream/`

### UserInputLog

```json
{
  "session_id": "xxx",
  "cycle_index": 0,
  "user_input": "查询上个月销售额"
}
```

**用于**: `POST /api/log-user-input/`

### CommentUpdate

```json
{
  "comment": "新的表注释"
}
```

**用于**: `PUT /api/comment-manage/{table_name}/table-comment`、`PUT /api/comment-manage/{table_name}/column/{column_name}/comment`

### KnowledgeEntry

```json
{
  "key": "数据库命名规范",
  "value": "表名使用小写蛇形命名"
}
```

**用于**: `POST /api/sys-knowledge/{resource}/`（所有 CRUD 资源）

### KnowledgeUpdate

```json
{
  "key": "新键名",
  "value": "新值"
}
```

两个字段可选，只更新提供的字段。

**用于**: `PUT /api/sys-knowledge/{resource}/{item_id}`

### BriefInfoUpdate

```json
{
  "value": "PostgreSQL"
}
```

**用于**: `PUT /api/sys-knowledge/brief-info/{attr}`

### DocumentInput

```json
{
  "conversation_history": [...],
  "session_id": "xxx"
}
```

**用于**: `POST /api/generate-document/stream/`、`POST /api/generate-document/stream/unified/`

### YamlOutlineInput

```json
{
  "conversation_history": [...],
  "session_id": "xxx",
  "user_prompt": "生成一份关于销售分析的报告"
}
```

**用于**: `POST /api/generate-document/generate-yaml-outline/`

### YamlDocumentInput

```json
{
  "conversation_history": [...],
  "yaml_outline": {"title": "...", "sections": [...]},
  "session_id": "xxx",
  "section_index": null,
  "confirmed_sections": [],
  "yaml_base": "outline_xxx"
}
```

`section_index` 为 `null` 时生成全部章节。

**用于**: `POST /api/generate-document/stream/from-yaml/`

### FinalizeInput

```json
{
  "markdown_content": "# 报告\n...",
  "session_id": "xxx",
  "yaml_base": "outline_xxx",
  "conversation_history": [...]
}
```

**用于**: `POST /api/generate-document/finalize/`

---

## 5. 数据库日志表结构

### session_operation_log — 操作日志

```sql
id            INT AUTO_INCREMENT PRIMARY KEY
session_id    VARCHAR(255)
api_endpoint  VARCHAR(255)
question      LONGTEXT       -- 用户问题
ans           LONGTEXT       -- 返回结果
code          LONGTEXT       -- 生成的代码
result_type   VARCHAR(50)    -- success / error
msg           VARCHAR(512)   -- 结果描述
prompt_length INT            -- prompt 长度（token）
created_at    DATETIME
```

### observe_session_log — 会话级观察日志

```sql
id                   INT AUTO_INCREMENT PRIMARY KEY
session_id           VARCHAR(255)
question             LONGTEXT         -- 用户初始问题
status               VARCHAR(50)      -- 会话状态
total_cycles         INT              -- 总循环次数
total_tokens         INT              -- 总 token 消耗
conversation_history LONGTEXT         -- 完整上下文（JSON 数组）
trimmed_context      LONGTEXT         -- 裁剪后的上下文（JSON 数组）
created_at           DATETIME
updated_at           DATETIME
```

### observe_cycle_log — 单次循环日志

```sql
id              INT AUTO_INCREMENT PRIMARY KEY
session_id      VARCHAR(255)
cycle_index     INT
phase           VARCHAR(50)     -- think / execute / observe
sub_phase       VARCHAR(100)    -- filter_db / filter_func / plan / gen_code / exec_code / result
prompt          LONGTEXT        -- 发给 LLM 的 prompt
response        LONGTEXT        -- LLM 回复
user_decision   VARCHAR(50)     -- approve / reject / edit / skip
exec_code       LONGTEXT        -- 执行的代码
exec_result     LONGTEXT        -- 执行结果
exec_error      LONGTEXT        -- 执行错误
token_estimate  INT             -- token 估算
created_at      DATETIME
```

### report_generation_log — 文档生成日志

```sql
id          INT AUTO_INCREMENT PRIMARY KEY
session_id  VARCHAR(255)
file_name   VARCHAR(512)    -- 生成的文件名
chat_history LONGTEXT       -- 输入的对话历史（JSON）
outline     LONGTEXT        -- 生成的大纲
full_text   LONGTEXT        -- 生成的完整文本
created_at  DATETIME
```

---

## 6. 依赖说明 `requirement.txt`

| 库 | 用途 |
|---|------|
| `fastapi` | HTTP 框架 |
| `uvicorn` | ASGI 服务器 |
| `pydantic` | 请求/响应模型校验 |
| `SQLAlchemy` + `PyMySQL` + `cryptography` | MySQL 数据库 ORM |
| `openai` | LLM API 调用 |
| `httpx` | HTTP 客户端（MCP 及代理） |
| `pandas` | 数据处理 |
| `matplotlib` + `seaborn` | 图表绘制 |
| `Pillow` | 图片处理 |
| `PyPDF2` + `python-docx` | PDF/DOCX 文档解析 |
| `beautifulsoup4` | HTML 解析 |
| `ddgs` | DuckDuckGo 搜索 |
| `mcp` | MCP 官方 SDK（测试服务器用）|
| `PyYAML` | YAML 配置文件读取 |
| `PyJWT` | JWT（预留） |
| `python-multipart` | 文件上传 |
| `pygwalker` | 交互式可视化 |
| `markdown-pdf` | MD → PDF 转换 |
| `starlette` | FastAPI 底层 |

---

## 7. 前端构建配置

### `vue-front/package.json` scripts

| 命令 | 说明 |
|------|------|
| `npm run dev` | 启动 Vite 开发服务器，端口 5173，HMR 热更新 |
| `npm run build` | 构建生产包到 `dist/` |
| `npm run preview` | 本地预览构建后的 `dist/` |

### `vue-front/vite.config.js` 开发代理

| 前缀 | 代理目标 |
|------|----------|
| `/api` | `VITE_SERVER_URL`（默认 `http://127.0.0.1:8008`）|
| `/upload-csv` | 同上 |
| `/upload-txt` | 同上 |
| `/tmp_imgs` | 同上 |

路径别名: `@` → `./src`

---

## 8. `front.py` 轻量部署

替代 nginx 的开发/生产部署方案，详见 `front.py`。

**环境变量**:

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BACKEND_URL` | `http://127.0.0.1:8008` | 后端服务地址 |
| `FRONT_HOST` | `0.0.0.0` | 监听地址 |
| `FRONT_PORT` | `8008` | 监听端口 |

**功能**:
- 从 `vue-front/dist/` 提供静态文件
- 代理 `/api`、`/upload-csv`、`/upload-txt`、`/tmp_imgs` 到后端
- SSE 流式响应透传（`/api/*/stream/`）
- SPA fallback 到 `index.html`