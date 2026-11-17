# Data Copilot v10

✨ **基于代码生成的多智能体数据分析平台**

通过自然语言与数据库交互，自动理解用户意图，将复杂问题拆解为子任务，通过 T-A-A-O 自主循环（Think → Action → Act → Observe）逐步完成 SQL 查询、代码生成执行、图表绘制与报告生成。支持多源知识库蒸馏、联网搜索、CSV 一键导入与全链路可观测。

### 相关项目
- [基于大语言模型的可解释型自然语言数据库查询系统](https://github.com/bytesc/data-copilot-steps)
- [基于大语言模型和并发预测模型的自然语言数据库查询系统](https://github.com/bytesc/data-copilot-v2)

[个人网站：www.bytesc.top](http://www.bytesc.top)

## 功能简介

- **自然语言驱动分析**：直接提问，自动生成并执行 SQL 和 Python 代码完成查询与可视化
- **T-A-A-O 自主闭环**：Think（规划）→ Action（决策）→ Act（执行）→ Observe（审查），循环直到任务完成
- **多智能体角色分工**：规划、执行、审查等角色分离，协同完成复杂任务流水线
- **代码生成与执行**：动态生成 Python 代码，默认在一次性隔离沙箱子进程中执行（`enable_code_sandbox`：AST 审查 + 资源上限 + 文件/网络白名单；设为 `false` 才回退到主进程直接执行），支持 SQL 查询、图表绘制、数据变换
- **智能图表绘制**：自动选择图表类型（matplotlib/seaborn），支持对比图、数据标注
- **知识蒸馏与检索**：多源知识库（业务规则、查询指南、思维策略、代码范例），动态注入上下文
- **上下文智能裁剪**：按类别独立保留策略，避免长对话上下文溢出
- **Blackboard 探索缓存**：explore_schema / explore_functions / explore_base_knowledge / explore_mcp 的完整结果存入 history 的 blackboard，独立注入所有 LLM 阶段，上下文只保留参数、计划和选中项；blackboard 另设 `recent_generated_images`（最近一次代码执行生成的图片）与 `selected_images`（`select_images` 选中或用户上传的图片及原因）两个图片区域，随 `## Blackboard` 段喂给 LLM，模型支持多模态时还会作为 `image_url` 提交（前端 Images 开关控制）。详见 [`docs/conversation_history_structure.md`](docs/conversation_history_structure.md)
- **文档自动生成**：一键生成 Markdown / DOCX / PDF 格式分析报告，含图表的智能排版
- **任意 CSV 导入**：上传 CSV 自动建表，上传文档自动生成数据注释
- **联网搜索**：支持 DuckDuckGo 联网搜索，结合外部信息分析
- **MCP 外部工具集成**：通过 Model Context Protocol 连接外部 MCP 服务器，扩展 LLM 能力边界（如调用外部 API、访问第三方服务）
- **全链路可观测**：每一步 LLM 调用、代码执行、结果均记录到数据库，支持会话回溯
- **SSE 实时流式**：生成代码、执行结果、规划更新实时推送到前端

## 技术架构

### 核心循环：T-A-A-O

```
┌─────────┐     ┌──────────┐     ┌──────┐     ┌──────────┐
│  THINK  │────▶│  ACTION  │────▶│  ACT │────▶│  OBSERVE │
│ (规划)   │     │ (决策)    │     │(执行) │     │ (审查)    │
└─────────┘     └──────────┘     └──────┘     └──────────┘
     ▲                                              │
     └──────────────────────────────────────────────┘
                    (循环直到任务完成)
```

每个阶段对应独立的 LLM 调用和专用提示词：

1. **THINK（思考）**：LLM 接收用户问题、数据库/函数简况（Brief Info）、思维知识库、对话上下文与 Blackboard，输出 JSON 规划 `{"description": "...", "todo": ["task1", ...]}`
2. **ACTION（决策）**：LLM 根据当前规划选择一个动作（探索表结构、生成代码、搜索知识库、搜索网页、反问用户、生成文档等）
3. **ACT（执行）**：执行所选动作——生成并执行代码、查询数据库、绘制图表、搜索网页等
4. **OBSERVE（审查）**：LLM 审查执行结果，更新任务列表，处理错误，决定继续或终止

![](./readme_img/flow-v10.png)

### 组件架构

| 组件 | 说明 |
|------|------|
| **LLM 主干** | 支持 DeepSeek、Qwen、GLM、GPT-4o 等，通过 OpenAI 兼容接口接入 |
| **函数图谱** | 预定义工具函数（SQL 查询、图表绘制、数据分析、地图/地理查询、HDB 预测等），LLM 动态选择组合 |
| **知识库** | 多源知识：业务规则（DB + 文件）、查询指南、思维策略、代码范例、数据库摘要 |
| **代码引擎** | 生成 Python 代码 → 一次性隔离沙箱子进程执行（默认，`enable_code_sandbox`）→ 结果流式返回 |
| **数据库层** | 用户数据 DB（MySQL）+ 系统 DB（会话日志、知识库、操作审计） |
| **文档生成器** | 大纲规划 → 逐节生成 → 多格式导出（MD/DOCX/PDF） |
| **前端** | Vue 3 + Vite，SSE 流式渲染，T-A-A-O 状态机 |

### 工作流程

```
用户提问 → [THINK] 规划任务列表
            → [ACTION] 决策动作
              → [ACT] 执行动作（探索/查询/画图/搜索/生成文档等）
                → [OBSERVE] 审查结果，更新任务列表
                  → 循环直到任务全部完成
```

**聊天模式切换**（输入框上方开关）：
- **Think 模式** — 完整 T-A-A-O 流程（Think → Action → Act → Observe）
- **Chat 模式** — 仅 Action → Act，跳过 Think/Observe，响应更快

### 工具函数

以下为 `agent/tools/get_function_info.py` 的 `FUNCTION_DICT` 实际暴露给 LLM 的函数（`search_web`、`fetch_webpage` 等已在字典中被注释禁用）：

| 函数 | 功能 |
|------|------|
| `exe_sql(sql)` | 执行 SQL 查询字符串，返回 pandas DataFrame |
| `explain_data(question, data, col_explanation=None)` | 对传入的 DataFrame 按自然语言问题输出分析说明 |
| `load_data(url)` | 从 CSV 文件 URL（如 `./tmp_imgs/xxx.csv`）加载数据 |
| `get_save_image_path()` | 获取保存图表 PNG 的唯一路径（位于 `tmp_imgs/`） |
| `predict_hdb_price(from_date=None, to_date=None, ...)` | 基于历史数据预测 HDB 转售价格，返回预测 DataFrame 与历史/预测对比图路径 |
| `get_onemap_static_map(layerchosen="default", latitude=None, longitude=None, postal=None, ...)` | 调用 OneMap.sg PNG API 生成静态地图图片 |
| `get_osm_minimap(markers=None, zoom=15, width=480, height=480)` | 生成 OpenStreetMap 带标记迷你地图 iframe |
| `get_streetdirectory_minimap(urls=None, width=800, height=480)` | 由 StreetDirectory 地点页 URL 生成迷你地图 iframe |
| `get_streetdirectory_static_map(urls=None, width=800, height=600)` | 渲染 StreetDirectory 地点页并截图保存为静态地图 PNG |
| `search_streetdirectory(query)` | 在新加坡 StreetDirectory 按邮编或地址检索地点 URL |
| `exe_mcp(server, tool, params=None)` | 调用 MCP 外部服务器上的指定工具 |

### 动作类型

| 动作 | 功能 | 可关闭 |
|------|------|--------|
| `explore_schema` | 探索数据库表结构 | 否 |
| `explore_functions` | 探索可用函数目录 | 否 |
| `explore_base_knowledge` | 搜索业务领域知识库 | 是（`enable_base_knowledge`） |
| `explore_mcp` | 探索外部 MCP 服务器的可用工具列表 | 是（`enable_mcp`） |
| `exe_mcp` | 调用外部 MCP 服务器上的具体工具 | 是（`enable_mcp`） |
| `generate_and_execute` | 生成并执行代码（SQL/Python） | 否 |
| `ask_question` | 反问用户以获取必要信息 | 否 |
| `ask_choice` | 给出若干选项供用户单选 | 否 |
| `summary_and_pause` | 输出进度总结并暂停流程 | 否 |
| `attempt_completion` | 输出最终结果并结束流程 | 否 |
| `select_images` | 设置 `selected_images` 区域，保存选中图片（文件名或 URL）及一句话原因，供后续多模态查看 | 否 |
| `web_search` | DuckDuckGo 联网搜索 | 是（`enable_web_search`） |
| `fetch_webpage` | 抓取网页内容 | 是（`enable_fetch_url`） |
| `generate_document` | 自动生成分析报告（MD/DOCX/PDF） | 否 |

## 配置与使用

### 环境要求

- Python 3.10
- MySQL 数据库

### 安装依赖

```bash
pip install -r requirement.txt
```

### 初始化系统数据库

`init.sql` 包含各系统表的 `CREATE TABLE` 语句（不创建数据库）以及 4 条 `brief_info` 初始化 `INSERT` 语句，需在 `config/config.yaml` 里 `mysql_sys` 指定的系统库中执行，例如 `data_copilot_v10_land_sys`。注意 `init.sql` 本身不建库，需先创建该库，再用库名把表建到其中（否则会报 `No database selected`）：

```bash
# 1) 创建系统库（库名需与 config/config.yaml 的 mysql_sys 一致）
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS data_copilot_v10_land_sys DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
# 2) 在该库中建表并初始化 brief_info
mysql -u root -p data_copilot_v10_land_sys < init.sql
```

`main.py` 启动时也会自动创建缺失的系统表（`CREATE TABLE IF NOT EXISTS`，重复执行安全）；其中 `base_knowledge`、`doc_guide`、`code_guide`、`graph_code_guide`、`think_guide` 这批知识表仅在 `enable_base_knowledge` 为 true 时创建。

> Docker Compose 部署使用 `docker/docker-init.sql`（它会建库并创建系统表，库名与 `config/config.yaml` 一致）；上面的 `init.sql` 仅用于非容器的手动部署。

### 配置文件

`./config/config.yaml`

```yaml
server_port: 8008
server_host: "0.0.0.0"

# 用户数据数据库（查询分析，同时供需修改数据库的功能使用）
mysql: "mysql+pymysql://root:123456@localhost:3306/singapore_land_2"
# 业务数据库只读用户（可选）：exe_sql 的 SELECT/SHOW 使用该账号；留空或删除则不启用只读查询（不会回退到 mysql，exe_sql 将被禁用）
mysql_readonly: "mysql+pymysql://readonly:123456@localhost:3306/singapore_land_2"
# 系统数据库（会话日志、知识库等）
mysql_sys: "mysql+pymysql://root:123456@localhost:3306/data_copilot_v10_land_sys"

# 单条 SQL 超时秒数（业务库 SELECT 最长执行时间）；业务库连接 socket 读写超时秒数（缺省 300，0 关闭）
sql_query_timeout: 60
sql_socket_timeout: 300

# 静态文件服务地址（文件固定存储于项目根目录 tmp_imgs/，不可配置）
static_path: "http://127.0.0.1:8008/"

# 大模型配置（多模型，前端可切换，列表第一个为默认；supports_images 控制图片多模态）
llm_models:
  - id: "deepseek-v4.1-flash"
    name: "DeepSeek V4.1 Flash"
    model: "deepseek-v4.1-flash"
    url: "https://tokenhub.tencentmaas.com/v1"
    key_file: "api_key_openai.txt"
    supports_images: true
    reasoning_effort: ["none", "low", "high", "max"]
    style_temperature: {Formal: 0.2, Casual: 0.7, Technical: 0.1}
    extra_params: {"max_tokens": 393216}

# 功能开关（设为 false 关闭对应能力）
enable_mcp: true              # MCP 外部工具集成
enable_base_knowledge: true   # 基础知识库检索
enable_target_knowledge: false # 目标文档模板知识（target_knowledge.md）注入 Think/Observe/代码生成等提示词
enable_web_search: true       # 联网搜索
enable_fetch_url: true        # 网页内容抓取
enable_web_access_log: true   # 记录 web_search / fetch_webpage 调用到系统库 web_access_log 表（session_id、关键词/URL、成功与否、耗时、结果 JSON）
enable_edit: true             # 数据/知识管理页（设为 false 时前端隐藏 Data、Knowledge 页面，后端对应接口返回 403）
max_steps: 999                # 前端 Agent 循环步数上限（0 表示不限制；由前端按本值控制，后端仅返回该配置）
enable_code_sandbox: true     # LLM 生成代码走沙箱子进程（推荐）；false=主进程直接 exec（旧行为，无隔离）
enable_perf_log: true         # 写接口性能指标到 perf_log.csv
enable_llm_log: true          # 记录每次 LLM 调用到系统库 llm_log 表（token 统计、首字符延迟、总耗时等）
enable_llm_tph_limit: false   # 开启 LLM 每小时 token 总量控制（按 llm_log 近 60 分钟用量，超限接口返回 429）
llm_tph_limit: 1000000        # 每小时允许的 token 数（enable_llm_tph_limit 为 true 时生效；0 表示不限制）
enable_sandbox_log: true      # 写沙箱审计日志到 sandbox_audit.log（每次沙箱启动/每次拒绝）
```

> 以上为**常用字段精简示例**；多模型/Depth/Style/`extra_params` 的完整字段说明见
> [`docs/config_and_models.md`](docs/config_and_models.md)。
> LLM 代码执行沙箱（资源上限 / 文件访问与网络白名单）的设置**不在本文件**，而在
> **`config/sandbox.yaml`**（见 [`docs/code_execution_sandbox.md`](docs/code_execution_sandbox.md)）。

### 请求格式（统一信封）

JSON `POST/PUT/PATCH` 请求可选使用 `{meta, data}` 信封（模型调用选项只能通过信封传入）：携带信封时，`meta` 放模型调用选项，`data` 放原接口参数，后端解包后把 `data` 转发给原接口；未携带信封的普通 JSON 请求原样透传：

```json
{
  "meta": {
    "model": "glm-5.3-flash",
    "reasoning_effort": "max",
    "style": "Casual"
  },
  "data": {
    "question": "分析上个月销售趋势",
    "session_id": "xxx"
  }
}
```

- `reasoning_effort` / `style` 为空字符串表示 `Default`。
- 后端不记忆选择；浏览器用 localStorage 的 `data-copilot-llm-config` 保存模型配置列表和当前选择。
- 启动时从后端动态获取配置列表；若与浏览器缓存不一致，或选择项已无效，则回退默认值（第一个模型、第一个 Depth、`Default` Style）。
- GET/DELETE 无请求体，不使用信封。
- Multipart 上传无法使用 JSON 信封，前端在 `FormData` 中附加 `meta` 字段（目前 `/upload-txt/` 会读取）。

### 前端配置

`vue-front/.env`

```env
VITE_API_BASE=/api
# 仅 npm run dev 的 Vite 反向代理目标；非 VITE_ 前缀，不注入客户端产物
DEV_PROXY_TARGET=http://127.0.0.1:8008
```

> 前端通过**同源相对地址**访问后端 API，生产由 nginx / front.py 反向代理，无需（也不会）在构建时
> 固化后端地址；换服务器部署不必重新构建前端。后端生成的绝对 URL（文档下载链接、聊天正文中的
> 图表图片、交互图/CSV 链接、静态地图等）由 `static_path` 决定，部署时须设为浏览器可达地址。

### API Key 配置

每个模型通过 `key_file` 字段指定 key 文件（位于 `agent/utils/llm_access/` 目录，如 `api_key_openai.txt`、`api_key_qwen.txt`），未配置时默认使用 `api_key_openai.txt`。把对应 API Key 填入文件即可。

获取方式：
- [阿里云百炼](https://bailian.console.aliyun.com/)
- [DeepSeek](https://api-docs.deepseek.com/)
- [智谱 GLM](https://open.bigmodel.cn/)
- [OpenAI](https://platform.openai.com/)


### 启动

```bash
python main.py
```

也可通过 `front.py` 部署（替代 nginx，提供前端静态服务 + API 反向代理 + SSE 流式支持）。`front.py` 只做静态服务与反向代理，后端需另行启动：

```bash
cd vue-front && npm install && npm run build && cd ..   # 1) 构建前端产物
python main.py                                          # 2) 启动后端（另开一个终端）
python front.py                                         # 3) 启动前端反代
```

`front.py` 从 `vue-front/dist/` 提供静态文件，必须先 `npm run build`，否则页面为 404。
监听地址/端口、后端地址、超时等直接改 `front.py` 文件开头的常量（不读取环境变量）。

Docker 部署请见 [`docs/deployment.md`](docs/deployment.md)。

## 文档索引

| 文档 | 内容 |
|------|------|
| [`docs/api.md`](docs/api.md) | 全部 API 端点说明、统一请求信封、请求/响应格式、错误码 |
| [`docs/config_and_models.md`](docs/config_and_models.md) | 配置格式（config.yaml / .env）、Pydantic 请求模型、日志表结构、依赖说明、前端构建配置 |
| [`docs/deployment.md`](docs/deployment.md) | 部署指南：Docker Compose 与 front.py，端口、配置、数据库初始化、故障排查 |
| [`docs/code_execution_sandbox.md`](docs/code_execution_sandbox.md) | 代码执行沙箱（配置/防护/运维视角）：防护分层、`config/sandbox.yaml` 配置、错误类型、审计日志、跨平台与能力边界 |
| [`docs/sandbox_init_and_lifecycle.md`](docs/sandbox_init_and_lifecycle.md) | 代码执行沙箱（实现视角）：父/子进程准备与启动、`exec` 前初始化顺序、JSON-lines 协议、收尾 |
| [`docs/mcp_servers.md`](docs/mcp_servers.md) | MCP 服务器配置与启动指南（mcp_servers.yaml、测试服务器、新增步骤） |
| [`docs/sse_event_flow.md`](docs/sse_event_flow.md) | SSE 流式事件类型与数据格式 |
| [`docs/context_overflow_handling.md`](docs/context_overflow_handling.md) | 上下文超长（Context Overflow）处理机制 |
| [`docs/conversation_history_structure.md`](docs/conversation_history_structure.md) | 对话历史结构定义 |
| [`docs/actions_input_output.md`](docs/actions_input_output.md) | Action 的输入输出规范 |
| [`docs/document_generation.md`](docs/document_generation.md) | 文档生成流程 |
| [`docs/upload_csv_and_doc.md`](docs/upload_csv_and_doc.md) | CSV 和文档上传说明 |
| [`docs/prompt_injection.md`](docs/prompt_injection.md) | 动态提示词注入机制（上下文注入说明） |
| [`docs/how_to_add_action.md`](docs/how_to_add_action.md) | 新增 Action 开发指南 |
| [`docs/how_to_add_function.md`](docs/how_to_add_function.md) | 新增 Function 开发指南 |
| [`docs/how_to_write_brief.md`](docs/how_to_write_brief.md) | 编写 Brief Info 规范 |
| [`docs/how_to_modify_db_and_knowledge.md`](docs/how_to_modify_db_and_knowledge.md) | 数据库与知识库修改说明 |
| [`vue-front/README.md`](vue-front/README.md) | Vue 前端开发与构建说明 |
| [`vue-front/docker.md`](vue-front/docker.md) | 前端 Docker 部署 |
| [`mcpserver/README.md`](mcpserver/README.md) | MCP 测试服务器说明 |

## 开源许可

MIT License

Copyright (c) 2025 bytesc