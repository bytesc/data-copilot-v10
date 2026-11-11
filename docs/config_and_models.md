# 配置与模型格式

## 1. 系统配置 `config/config.yaml`

```yaml
# 服务端口与绑定地址
server_port: 8008
server_host: "0.0.0.0"

# 用户业务数据库（用于查询分析，同时供需修改数据库的功能使用，如建表、改注释、导入）
mysql: "mysql+pymysql://root:123456@localhost:3306/singapore_land_2"

# 业务数据库只读用户（可选）：exe_sql 执行 SELECT/SHOW 等只读 SQL 时使用该账号，
# 仅需 SELECT、SHOW VIEW 权限（可 show 表与视图）；留空或删除则不再启用只读查询（不会回退到 mysql，exe_sql 将被禁用）。
mysql_readonly: "mysql+pymysql://readonly:123456@localhost:3306/singapore_land_2"

# 系统数据库（会话日志、知识库、操作审计）
mysql_sys: "mysql+pymysql://root:123456@localhost:3306/data_copilot_v10_land_sys"

# 静态文件 URL 前缀（部署时改为服务器实际地址，如 http://your-server-ip:8038/）
# 以本文件为唯一来源，不读取任何环境变量。
static_path: "http://127.0.0.1:8008/"
# 静态文件固定存储在项目根目录 tmp_imgs/ 下（不可配置）

# 大模型（多模型配置，前端可选择切换，列表第一个为默认）
llm_models:
  - id: "deepseek-v4.1-flash"            # 唯一标识（默认取 name），供前端切换接口引用
    name: "DeepSeek V4.1 Flash"          # 自定义模型名称（前端下拉框显示）
    model: "deepseek-v4.1-flash"         # 实际调用的模型名称
    url: "https://tokenhub.tencentmaas.com/v1"  # OpenAI 兼容接口地址
    key_file: "api_key_openai.txt"       # key 文件名（agent/utils/llm_access/ 目录下），不填用默认 api_key_openai.txt
    supports_images: true                # 是否支持图片多模态输入；为 true 时会把 blackboard recent_generated_images / selected_images 区域的图片随请求上传
    reasoning_effort: ["none", "low", "high", "max"]  # 前端 Depth 下拉选项，默认选中第一个；不填/[] 则该项不可用
    style_temperature: {Formal: 0.2, Casual: 0.7, Technical: 0.1}  # 前端 Style 下拉，默认 Default；不填/{} 则该项不可用
    extra_params: {"max_tokens": 393216}  # 该模型专属额外请求参数
  - id: "deepseek-v4-flash"
    name: "DeepSeek V4 Flash"
    model: "deepseek-v4-flash"
    url: "https://tokenhub.tencentmaas.com/v1"
    key_file: "api_key_openai.txt"
    supports_images: false
    reasoning_effort: ["none", "low", "high", "max"]
    style_temperature: {Formal: 0.2, Casual: 0.7, Technical: 0.1}
    extra_params: {"max_tokens": 393216}
  - id: "glm-5.3-flash"
    name: "glm5.3 flash"
    model: "glm-5.3-flash"
    url: "https://tokenhub.tencentmaas.com/v1"
    key_file: "api_key_openai.txt"
    supports_images: true
    style_temperature: {Formal: 0.2, Casual: 0.7, Technical: 0.1}
    extra_params: {}                     # {} 或删除表示使用模型默认行为；无对应选项时下拉禁用
  - id: "glm-5.3-flashx"
    name: "glm5.3 flashx"
    model: "glm-5.3-flashx"
    url: "https://tokenhub.tencentmaas.com/v1"
    key_file: "api_key_openai.txt"
    supports_images: true
    reasoning_effort: ["low", "high", "max"]
    extra_params: {}

# Depth 默认选中列表第一个，Style 默认选中 Default（不额外上传 reasoning_effort/temperature）。
# extra_params 若也含 reasoning_effort 或 temperature，最终合并时以 extra_params 为准。
# supports_images 未配置时默认 false；为 true 时前端 Images 开关可用且默认开启，
# 请求会把 blackboard recent_generated_images / selected_images 区域中的图片作为 image_url 内容提交给模型（recent_generated_images 在前，selected_images 在后；selected_images 含 `select_images` 选中与用户上传的图片）。
# 请求 meta.use_images=false 可临时关闭图片提交；不支持的模型开关置灰且始终不提交图片。

# extra_params 说明（各模型单独配置，透传给 OpenAI 兼容接口的扩展字段）：
# DeepSeek 官方文档（api-docs.deepseek.com/zh-cn/guides/thinking_mode）：
#   关闭思考  -> {"thinking": {"type": "disabled"}}
#   思考强度  -> reasoning_effort: "none" / "low" / "high" / "max"
# 其他厂商（参数各不相同，网关可能透传/忽略/报错）：
#   GLM-5.3          -> {"thinking": {"type": "enabled"}, "reasoning_effort": "low"|"high"|"max"}（默认 max）
#   OpenAI gpt-5/o 系-> 无法完全关闭，用 {"reasoning_effort": "low"}
# 设 {} 或删除该项则保持模型默认行为

# 功能开关
enable_mcp: true              # MCP 外部工具
enable_base_knowledge: true   # 基础知识库检索
enable_target_knowledge: false # 目标文档模板知识（target_knowledge.md）注入 Think/Observe/代码生成等提示词
enable_web_search: true       # 联网搜索
enable_fetch_url: true        # 网页内容抓取
enable_edit: true             # 数据/知识编辑（设为 false 时前端隐藏 Data、Knowledge 页面，后端对应接口返回 403）
enable_llmlog: false           # 记录 LLM 调用日志到 llmlog/*.txt
enable_perf_log: true          # 写接口性能指标到 perf_log.csv
```

> 图片能力需以模型供应商实际支持为准。当前仓库配置中 `deepseek-v4.1-flash`、`glm-5.3-flash`、`glm-5.3-flashx` 已开启 `supports_images: true`；`deepseek-v4-flash` 为 `false`。

**DSN 格式**: `mysql+pymysql://用户名:密码@主机:端口/数据库名`

> **只读用户说明**：`mysql_readonly` 用于**所有只读查询**——既包括 `exe_sql` 执行的 SELECT/SHOW，也包括探索类读取（`explore_schema` 的库结构/样例、字段筛选、`plain_chat`、`predict_hdb_price` 等，均通过 `read_only_engine` 走该账号）；建表、改注释、导入等改库功能仍使用 `mysql`。当 `mysql_readonly` 缺失时 `exe_sql` 被禁用（不回退特权账号），但 `read_only_engine` 会回退到主账号 `mysql` 以保证探索类读取仍可用。
> 创建只读账号（仅需可 show 表和视图）：
> ```sql
> CREATE USER 'readonly'@'%' IDENTIFIED BY '123456';
> GRANT SELECT, SHOW VIEW ON singapore_land_2.* TO 'readonly'@'%';
> FLUSH PRIVILEGES;
> ```
> `SELECT` 覆盖查询与 `SHOW TABLES/COLUMNS`，`SHOW VIEW` 覆盖视图定义（`SHOW CREATE VIEW`）。

**单一来源**：以上配置项**只**来自本文件，程序不读取任何环境变量；`static_path`、`server_host`/`server_port`、`mysql*` 等如需变更，请直接修改本文件并重启（Docker 部署需重建镜像）。

---

## 2. 前端环境变量 `vue-front/.env`

```env
VITE_API_BASE=/api
DEV_PROXY_TARGET=http://127.0.0.1:8008
```

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VITE_API_BASE` | `/api` | API 路径前缀（`VITE_` 前缀会被注入到客户端产物） |
| `DEV_PROXY_TARGET` | `http://127.0.0.1:8008` | **仅** `npm run dev` 的 Vite 反向代理目标；非 `VITE_` 前缀，不注入客户端 |

`vite.config.js` 将 `/api`、`/upload-csv`、`/upload-txt`、`/tmp_imgs` 代理到 `DEV_PROXY_TARGET`
指定的后端。生产环境由 `front.py` 或 nginx 承担相同代理职责，浏览器端一律使用**同源相对
地址**（`window.location.origin`），因此**不会把后端地址固化进产物**，无需为不同服务器重新构建。
后端生成的绝对 URL（文档下载链接、聊天正文中的图表图片、交互图/CSV 链接、静态地图等）由后端
`static_path` 拼接、经 SSE 下发后由前端渲染，部署时须把 `config/config.yaml` 的 `static_path` 设为
浏览器可达的前端地址（nginx 与 front.py 均透传 `/tmp_imgs/`）。

---

## 3. MCP 服务器

配置与启动详见独立文档 [MCP 服务器指南](mcp_servers.md)（`config/mcp_servers.yaml`、`mcpserver/` 下的启动方式与新增步骤）。

---

## 4. 请求模型（Pydantic Schemas）

### 统一请求信封

JSON `POST/PUT/PATCH` 的 HTTP 请求体可选使用 `{meta, data}` 信封（模型调用选项只能通过信封传入）；不携带信封的普通 JSON 原样透传。携带信封时请求体为：

```json
{
  "meta": {
    "model": "glm-5.3-flash",
    "reasoning_effort": "max",
    "style": "Casual",
    "use_images": true
  },
  "data": {
    "question": "分析上个月销售趋势",
    "session_id": "xxx"
  }
}
```

- `meta` 只包含模型调用选择：`model`、`reasoning_effort`、`style`、`use_images`；为空字符串表示 `Default`。
- `use_images` 控制是否随请求上传 blackboard 图片，仅对 `supports_images` 为 true 的模型生效；未携带时按模型能力取默认值（支持则为 true，不支持则为 false）。前端 Images 开关的状态会缓存在 localStorage 并随每次请求发送。
- 后端中间件读取 `meta` 后只把 `data` 交给原 Pydantic 接口，因此下文各请求模型的示例均表示 `data` 内容。
- 未使用信封的普通 JSON 请求原样透传（不会返回 `400`），但无法携带模型调用选项；也没有 header 回退。
- 后端不保存用户选择；浏览器用 localStorage 的 `data-copilot-llm-config` 缓存模型配置列表和当前选择，并在每次请求中发送。
- 启动时从后端动态获取配置列表；若与浏览器缓存不一致，或选择的模型/Depth/Style 已无效，则回退默认值（第一个模型、第一个 Depth、`Default` Style）。
- GET/DELETE 没有请求体，不使用信封。
- Multipart 上传使用 `meta` 表单字段，目前仅 `/upload-txt/` 读取并用于 LLM 注释生成。

### AgentInput — 通用 Agent 请求

```json
{
  "question": "分析上个月销售趋势",
  "tables": ["orders", "products"],
  "selected_fields": {"orders": ["amount", "date"]},
  "selected_functions": ["exe_sql", "get_save_image_path"],
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

**用于**: `POST /api/generate-and-execute/stream/`、`POST /api/plain-chat/stream/`、`POST /api/filter-db-fields/stream/`、`POST /api/filter-db-fields/`、`POST /api/filter-functions/stream/`、`POST /api/exe-sql/`

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

`action` 可选值: `explore_schema`, `explore_functions`, `generate_and_execute`, `ask_question`, `ask_choice`, `summary_and_pause`, `attempt_completion`, `generate_document`, `select_images`；以及按配置开关追加的 `explore_base_knowledge`（`enable_base_knowledge`）、`web_search`（`enable_web_search`）、`fetch_webpage`（`enable_fetch_url`）、`explore_mcp` / `exe_mcp`（`enable_mcp`）。

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
  "yaml_outline": "title: ...\nsections: [...]",
  "session_id": "xxx",
  "section_index": null,
  "confirmed_sections": [],
  "yaml_base": "outline_xxx"
}
```

`yaml_outline` 为 YAML 文本字符串（字段类型 `str`，即上面 JSON 示例中的字符串值）；`section_index` 为 `null` 时生成全部章节。

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
prompt_length INT            -- prompt 长度（字符数，作为 token 的粗略估算）
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
conversation_history LONGTEXT         -- 完整历史（JSON 数组，含 blackboard）
trimmed_context      LONGTEXT         -- 裁剪后的普通上下文（JSON 数组，不含 blackboard）
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
user_decision   VARCHAR(2000)   -- approve / reject / edit / skip 或用户输入文本（最多 2000 字；旧表的 VARCHAR(50) 在启动时自动加宽）
exec_code       LONGTEXT        -- 执行的代码
exec_result     LONGTEXT        -- 执行结果
exec_error      LONGTEXT        -- 执行错误
token_estimate  INT             -- token 估算
created_at      DATETIME
```

> 上表 `phase` / `sub_phase` 的注释为建表时的历史描述，实际写入值随实现演进：`phase` 实际为 `think` / `action` / `act` / `observe` / `execute`（`/api/exe-sql/`）以及 `generate_document` / `generate_document_unified` / `generate_yaml_outline` / `generate_from_yaml` / `user`；`sub_phase` 实际为 `plan` / `decide` / `review` / `explore_*` / `generate_and_execute` / `web_search` / `fetch_webpage` / `exe_mcp` / `select_images` / `ask_question` 等。

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

### 系统库知识表

系统库另含 6 张键值对知识表：`base_knowledge`、`db_query_guide`、`code_guide`、`graph_code_guide`、`think_guide`、`doc_guide`，结构均为 `id` INT 主键、`key` TEXT、`value` LONGTEXT（`init.sql` 与 `docker/docker-init.sql` 均已包含这 6 张表）。

---

## 6. 依赖说明 `requirement.txt`

| 库 | 用途 |
|---|------|
| `fastapi` | HTTP 框架 |
| `uvicorn` | ASGI 服务器 |
| `pydantic` | 请求/响应模型校验 |
| `SQLAlchemy` + `PyMySQL` + `cryptography` | MySQL 数据库 ORM |
| `openai` | LLM API 调用 |
| `httpx` | HTTP 客户端（`front.py` 反向代理、文档图片下载、`fetch_webpage` 抓取；MCP 客户端使用标准库 `urllib.request`）|
| `pandas` | 数据处理 |
| `matplotlib` + `seaborn` | 图表绘制 |
| `Pillow` | 图片处理 |
| `PyPDF2` + `python-docx` | PDF/DOCX 文档解析 |
| `beautifulsoup4` | HTML 解析 |
| `trafilatura` | 网页正文抽取（`fetch_webpage` 主内容提取，去除导航/页脚等噪声，依赖 lxml）|
| `ddgs` | DuckDuckGo 搜索 |
| `mcp` | MCP 官方 SDK（测试服务器用）|
| `PyYAML` | YAML 配置文件读取 |
| `numpy` | 数值计算（pandas / matplotlib 依赖）|
| `requests` | HTTP 请求 |
| `greenlet` | SQLAlchemy 运行依赖 |
| `PyJWT` | JWT（预留） |
| `python-multipart` | 文件上传 |
| `pygwalker` | 交互式可视化 |
| `markdown-pdf` | MD → PDF 转换 |
| `playwright` | 无头浏览器（`get_streetdirectory_static_map` 截图，需本机安装 Chrome）|
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
| `/api` | `DEV_PROXY_TARGET`（`vue-front/.env` 中配置为 `http://127.0.0.1:8008`）|
| `/upload-csv` | 同上 |
| `/upload-txt` | 同上 |
| `/tmp_imgs` | 同上 |

路径别名: `@` → `./src`

---

## 8. `front.py` 轻量部署

替代 nginx 的开发/生产部署方案，详见 `front.py`。

**前置条件**：`front.py` 只提供静态文件与反向代理，后端必须另行启动；且必须先构建前端产物，否则 `vue-front/dist/` 不存在、页面返回 404：

```bash
# 1) 构建前端产物
cd vue-front && npm install && npm run build && cd ..

# 2) 启动后端（另开一个终端）
python main.py

# 3) 启动前端反代
python front.py
```

**配置**（直接修改 `front.py` 文件开头的常量，不读取环境变量）：

| 常量 | 默认 | 说明 |
|------|------|------|
| `BACKEND_URL` | `""` | 后端服务地址；留空则按 `config/config.yaml` 的 `server_host`/`server_port` 推导（`0.0.0.0`/`::`/空 host 按 `127.0.0.1` 处理，即默认配置下为 `http://127.0.0.1:8008`） |
| `FRONT_HOST` | `"0.0.0.0"` | 监听地址 |
| `FRONT_PORT` | `8010` | 监听端口 |
| `PROXY_TIMEOUT` | `600.0` | 反代到后端的超时秒数（含 SSE 流） |

> 文档下载链接由后端 `static_path` 生成。用 `front.py` 部署时应把 `config/config.yaml` 的 `static_path` 设为 `http://<本机地址>:<FRONT_PORT>/`（端口与 `front.py` 的 `FRONT_PORT` 一致），否则下载链接指向后端 8008 端口。

**功能**:
- 从 `vue-front/dist/` 提供静态文件
- 代理 `/api`、`/upload-csv`、`/upload-txt`、`/tmp_imgs` 到后端
- SSE 流式响应透传：凡是路径含 `/stream/` 的都按流式转发；文档生成中不以 `/stream/` 结尾的流式路由（`generate-yaml-outline`、`finalize`）在 `front.py` 显式列出
- SPA fallback 到 `index.html`