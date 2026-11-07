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
- **代码生成与执行**：动态生成 Python 代码，安全沙箱执行，支持 SQL 查询、图表绘制、数据变换
- **智能图表绘制**：自动选择图表类型（matplotlib/seaborn），支持对比图、数据标注
- **知识蒸馏与检索**：多源知识库（业务规则、查询指南、思维策略、代码范例），动态注入上下文
- **上下文智能裁剪**：按类别独立保留策略，避免长对话上下文溢出
- **Blackboard 探索缓存**：explore_schema / explore_functions / explore_base_knowledge / explore_mcp 的完整结果存入 history 的 blackboard，独立注入所有 LLM 阶段，上下文只保留参数、计划和选中项；blackboard 另设 `rencent_generated_images` 区域保存最近一次代码执行生成的图片列表，`selected_images` 区域通过 `select_images` action 保存人工/模型选中的图片（文件名或 URL）及一句话选中原因，随 `## Blackboard` 段喂给 LLM。支持图片多模态的模型还会把图片作为 `image_url` 内容随请求提交（前端 Images 开关控制），本地图片/本机静态 URL 转 base64，外部 URL 原样传递；聊天记录 act 条目的 `images` 字段仅前端展示
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

1. **THINK（思考）**：LLM 接收用户问题、数据库结构、函数目录、知识库，输出 JSON 规划 `{"description": "...", "todo": ["task1", ...]}`
2. **ACTION（决策）**：LLM 根据当前规划选择一个动作（探索表结构、生成代码、搜索知识库、搜索网页、反问用户、生成文档等）
3. **ACT（执行）**：执行所选动作——生成并执行代码、查询数据库、绘制图表、搜索网页等
4. **OBSERVE（审查）**：LLM 审查执行结果，更新任务列表，处理错误，决定继续或终止

![](./readme_img/flow-v10.png)

### 组件架构

| 组件 | 说明 |
|------|------|
| **LLM 主干** | 支持 DeepSeek、Qwen、GLM、GPT-4o 等，通过 OpenAI 兼容接口接入 |
| **函数图谱** | 预定义工具函数（SQL 查询、图表绘制、数据分析、网页搜索等），LLM 动态选择组合 |
| **知识库** | 多源知识：业务规则（DB + 文件）、查询指南、思维策略、代码范例、数据库摘要 |
| **代码引擎** | 生成 Python 代码 → 沙箱执行 → 结果流式返回 |
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

以下为 `agent/tools/get_function_info.py` 的 `FUNCTION_DICT` 实际暴露给 LLM 的函数（`query_database`、`draw_graph`、`draw_compare_graph`、`search_web`、`fetch_webpage` 等已在字典中被注释禁用）：

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

`init.sql` 只包含 `CREATE TABLE` 语句（不创建数据库），需在 `config/config.yaml` 里 `mysql_sys` 指定的系统库中执行，例如 `data_copilot_v10_land_sys`：

```bash
mysql -u root -p < init.sql
```

`main.py` 启动时也会自动创建缺失的系统表，包括 `init.sql` 未包含的 `graph_code_guide`。

### 配置文件

`./config/config.yaml`

```yaml
server_port: 8008
server_host: "0.0.0.0"

# 用户数据数据库（查询分析，同时供需修改数据库的功能使用）
mysql: "mysql+pymysql://root:123456@localhost:3306/singapore_land_2"

# 业务数据库只读用户（可选）：exe_sql 的 SELECT/SHOW 使用该账号，仅需 SELECT、SHOW VIEW；留空回退到 mysql
mysql_readonly: "mysql+pymysql://readonly:123456@localhost:3306/singapore_land_2"

# 系统数据库（会话日志、知识库等）
mysql_sys: "mysql+pymysql://root:123456@localhost:3306/data_copilot_v10_land_sys"

# 静态文件服务地址
static_path: "http://127.0.0.1:8008/"
# 静态文件固定存储在项目根目录 tmp_imgs/ 下（不可配置）

# 大模型配置（多模型，前端可切换，列表第一个为默认）
llm_models:
  - id: "deepseek-v4.1-flash"
    name: "DeepSeek V4.1 Flash"        # 自定义模型名称（前端下拉框显示）
    model: "deepseek-v4.1-flash"       # 实际调用的模型名称
    url: "https://tokenhub.tencentmaas.com/v1"  # OpenAI 兼容接口地址
    key_file: "api_key_openai.txt"     # key 文件名（位于 agent/utils/llm_access/），不填用默认 api_key_openai.txt
    supports_images: true              # 是否支持图片多模态输入
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
    extra_params: {}
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

# extra_params 参考（各模型单独配置）：
# DeepSeek 关闭思考: {"thinking": {"type": "disabled"}}；调强度用 reasoning_effort: none/low/high/max
# GLM-5.3: {"thinking": {"type": "enabled"}, "reasoning_effort": "low"|"high"|"max"}（默认 max）
# OpenAI gpt-5/o 系：无法完全关闭，用 {"reasoning_effort": "low"}；设 {} 恢复默认

# 功能开关（设为 false 关闭对应能力）
enable_mcp: true              # MCP 外部工具集成
enable_base_knowledge: true   # 基础知识库检索
enable_web_search: true       # 联网搜索
enable_fetch_url: true        # 网页内容抓取
enable_edit: true             # 数据/知识管理页（设为 false 时前端隐藏 Data、Knowledge 页面，后端对应接口返回 403）
enable_llmlog: false          # 记录 LLM 调用日志到 llmlog/*.txt
enable_perf_log: true         # 写接口性能指标到 perf_log.csv
```

### 请求格式（统一信封）

所有 JSON `POST/PUT/PATCH` 请求必须使用 `{meta, data}` 信封；`meta` 放模型调用选项，`data` 放原接口参数：

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
VITE_SERVER_URL=http://127.0.0.1:8008
VITE_API_BASE=/api
```

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

也可通过 `front.py` 部署（替代 nginx，提供前端静态服务 + API 反向代理 + SSE 流式支持）：

```bash
FRONT_PORT=8010 python front.py
```

## 文档索引

| 文档 | 内容 |
|------|------|
| [`docs/api.md`](docs/api.md) | 全部 API 端点说明、统一请求信封、请求/响应格式、错误码 |
| [`docs/config_and_models.md`](docs/config_and_models.md) | 配置格式（config.yaml / .env）、Pydantic 请求模型、日志表结构、依赖说明、前端构建配置 |
| [`docs/mcp_servers.md`](docs/mcp_servers.md) | MCP 服务器配置与启动指南（mcp_servers.yaml、测试服务器、新增步骤） |
| [`docs/sse_event_flow.md`](docs/sse_event_flow.md) | SSE 流式事件类型与数据格式 |
| [`docs/context_overflow_handling.md`](docs/context_overflow_handling.md) | 上下文超长（Context Overflow）处理机制 |
| [`docs/conversation_history_structure.md`](docs/conversation_history_structure.md) | 对话历史结构定义 |
| [`docs/actions_input_output.md`](docs/actions_input_output.md) | Action 的输入输出规范 |
| [`docs/document_generation.md`](docs/document_generation.md) | 文档生成流程 |
| [`docs/upload_csv_and_doc.md`](docs/upload_csv_and_doc.md) | CSV 和文档上传说明 |
| [`docs/prompt_injection.md`](docs/prompt_injection.md) | 提示注入防护策略 |
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