# conversation_history 结构定义

`conversation_history` 是一个 JSON 数组，按发生顺序记录用户输入与 Agent 各阶段输出。数组元素统一为对象，基础字段为 `role`、`type`，其余字段随类型不同而不同。

逻辑上分为两部分：

- **blackboard 条目**：完整搜索结果，固定在数组第一个位置，包含 DB schema、函数文档、业务知识、MCP 工具详情、最近一次代码执行生成的图片列表，以及 `select_images` 选中或用户上传的图片及原因。
- **普通条目**：用户输入、`think`、`action_decision`、`act` 元数据、`observe` 等。

> **用户上传图片**：前端选择图片后先暂存在浏览器，点击发送时才随 `conversation_history` 的 user 条目的 `uploaded` 字段以 base64 一起提交（**不使用独立的 Multipart 上传接口**）。后端在请求信封中间件（`main.py` 的 `unified_request_envelope` → `utils/image_ingest.py` 的 `ingest_uploaded_images`）里解码、保存为 `tmp_imgs/upload_<8位小写字母>.png`，并把该字段改写成文件名列表、合并进 blackboard 的 `selected_images` 区域。处理是幂等的，已在同一请求内完成，因此后续阶段与持久化的都是文件名版本。

数据库中的两份数据：

- `conversation_history`：完整历史，包含 blackboard。
- `trimmed_context`：按保留策略裁剪后的普通条目，**不包含 blackboard**；实际送给 LLM 的上下文文本由它经 `history_to_text` 生成。

blackboard 不进入 `trimmed_context`，而是由 `utils/blackboard.py` 单独提取成 `## Blackboard` 段，注入所有 LLM 阶段。

基础形态：

```json
[
  {"role": "system", "type": "blackboard", "regions": {"schema": {}, "functions": {}, "knowledge": {}, "mcp": {}, "recent_generated_images": {}, "selected_images": {}}},
  {"role": "user", "type": "question", "content": "..."},
  {"role": "assistant", "type": "think", "content": {"description": "...", "todo": ["..."]}},
  {"role": "assistant", "type": "action_decision", "content": {"action": "..."}},
  {"role": "assistant", "type": "act", "action": "...", "...": "..."},
  {"role": "assistant", "type": "observe", "action": "被复盘动作", "content": {"description": "...", "todo": ["..."]}}
]
```

> `observe` 条目的 `action` 字段记录本次复盘对应的上一个 `act` 动作名（未识别到动作时省略），用于按动作区分 Observe 历史的裁剪保留策略。

## 完整示例

以下把所有条目类型和 `action_decision` 的可选字段放在同一个数组中，仅用于展示字段全集。真实记录中：

- 每个 `action_decision` 只携带当前 action 对应的字段，不会同时出现所有可选字段。
- 同一决策使用多动作时，用 `{"actions":[{...}, ...]}` 代替 `action`。
- 前端交互类动作在实时流程中通常只出现在 `action_decision.content`（网页前端本地渲染，不调用 `/api/act/stream/`）；API 调用方直接对这类动作请求 `/api/act/stream/` 时，`agent/act.py` 也会写出一条独立的 `act` 条目，但**不带** `needs_user_input`/`paused`/`completed` 等状态标记（这些标记只在由日志重建时补出，见「纯前端执行」）。

```json
[
  {
    "role": "system",
    "type": "blackboard",
    "regions": {
      "schema": {
        "selected_fields": {},
        "explore_plan": "探索计划",
        "selected_guides": [],
        "query_guide_content": "查询指南",
        "schema_detail": "数据库结构"
      },
      "functions": {
        "selected_functions": ["exe_sql"],
        "explore_plan": "探索计划",
        "func_docs": "函数文档"
      },
      "knowledge": {
        "selected_knowledge_ids": [1, 2],
        "summary": "摘要",
        "knowledge_content": "知识内容"
      },
      "mcp": {
        "selected_tools": [],
        "explore_plan": "探索计划",
        "tool_detail": "工具详情",
        "catalog": "工具目录"
      },
      "recent_generated_images": {
        "images": ["xxx.png"]
      }
    }
  },
  {
    "role": "user",
    "type": "question",
    "content": "用户原始问题"
  },
  {
    "role": "assistant",
    "type": "think",
    "content": {
      "description": "分析策略(markdown)",
      "todo": ["任务1", "任务2"]
    }
  },
  {
    "role": "assistant",
    "type": "action_decision",
    "content": {
      "action": "explore_schema",
      "keyword": "可选关键词",
      "text": "可选文本",
      "choices": ["可选选项"],
      "research_guide": "可选",
      "title": "可选",
      "query": "可选",
      "max_results": 10,
      "url": "可选",
      "max_length": 10000,
      "server": "可选",
      "tool": "可选",
      "params": {},
      "tools": []
    }
  },
  {
    "role": "assistant",
    "type": "act",
    "action": "explore_schema",
    "selected_fields": {},
    "explore_plan": "探索计划",
    "selected_guides": []
  },
  {
    "role": "assistant",
    "type": "act",
    "action": "explore_functions",
    "selected_functions": ["exe_sql"],
    "explore_plan": "探索计划"
  },
  {
    "role": "assistant",
    "type": "act",
    "action": "explore_base_knowledge",
    "selected_knowledge_ids": [1, 2],
    "summary": "摘要"
  },
  {
    "role": "assistant",
    "type": "act",
    "action": "generate_and_execute",
    "code": "生成的 Python 代码",
    "result": "执行输出",
    "images": ["xxx.png"]
  },
  {
    "role": "assistant",
    "type": "act",
    "action": "generate_and_execute",
    "code": "生成的 Python 代码",
    "error": "执行错误",
    "result": "可选的部分输出",
    "images": ["xxx.png"]
  },
  {
    "role": "assistant",
    "type": "act",
    "action": "generate_document",
    "title": "报告标题",
    "file_name": "文件名",
    "full_text": "文档全文",
    "download_url_md": "url",
    "download_url_docx": "url",
    "download_url_pdf": "url"
  },
  {
    "role": "assistant",
    "type": "act",
    "action": "web_search",
    "search_result": "搜索结果",
    "query": "搜索词"
  },
  {
    "role": "assistant",
    "type": "act",
    "action": "fetch_webpage",
    "page_content": "网页内容",
    "url": "https://example.com"
  },
  {
    "role": "assistant",
    "type": "act",
    "action": "explore_mcp",
    "selected_tools": [],
    "explore_plan": "探索计划"
  },
  {
    "role": "assistant",
    "type": "act",
    "action": "exe_mcp",
    "results": [
      {"server": "srv", "tool": "tool", "result": {}, "error": ""}
    ],
    "display_content": "展示文本",
    "error": "整体错误"
  },
  {
    "role": "assistant",
    "type": "act",
    "action": "ask_question",
    "text": "向用户提问",
    "needs_user_input": true
  },
  {
    "role": "assistant",
    "type": "act",
    "action": "ask_choice",
    "text": "请选择",
    "choices": ["选项A", "选项B"],
    "needs_user_input": true
  },
  {
    "role": "assistant",
    "type": "act",
    "action": "summary_and_pause",
    "text": "进度摘要",
    "paused": true
  },
  {
    "role": "assistant",
    "type": "act",
    "action": "attempt_completion",
    "text": "最终结果",
    "completed": true
  },
  {
    "role": "assistant",
    "type": "observe",
    "action": "generate_and_execute",
    "content": {
      "description": "复盘与更新后的策略",
      "todo": ["剩余任务1"]
    }
  },
  {
    "role": "user",
    "type": "choice",
    "content": "用户选择"
  },
  {
    "role": "user",
    "type": "response",
    "content": "用户回答"
  },
  {
    "role": "user",
    "type": "input",
    "content": "用户补充输入"
  },
  {
    "role": "assistant",
    "type": "document",
    "content": "重建历史时生成的文档内容"
  }
]
```

## blackboard

blackboard 是完整 history 的第一个元素，保存 explore 类动作选中的完整搜索结果、最近一次代码执行生成的图片列表，以及 `select_images` 选中的图片及原因。各 explore action 只把参数/计划/选中项写入对应的 `act` 条目，完整内容统一写入 blackboard 的对应区域。

```json
{
  "role": "system",
  "type": "blackboard",
  "regions": {
    "schema": {
      "selected_fields": {"table": ["col1"]},
      "explore_plan": "...",
      "selected_guides": [1, 3],
      "query_guide_content": "...",
      "schema_detail": "..."
    },
    "functions": {
      "selected_functions": ["exe_sql"],
      "explore_plan": "...",
      "func_docs": "..."
    },
    "knowledge": {
      "selected_knowledge_ids": [1, 2],
      "summary": "...",
      "knowledge_content": "..."
    },
    "mcp": {
      "selected_tools": [{"server": "calculator", "name": "calculate"}],
      "explore_plan": "...",
      "tool_detail": "...",
      "catalog": "..."
    },
    "recent_generated_images": {
      "images": [
        "xxx.png",
        "http://127.0.0.1:8008/tmp_imgs/yyy.png",
        "https://example.com/zzz.png"
      ]
    },
    "selected_images": {
      "images": [
        {"path": "xxx.png", "reason": "展示销售趋势，与当前分析目标一致"},
        {"path": "https://example.com/chart.png", "reason": "外部参考图，用于对比目标样式"}
      ]
    }
  }
}
```

| 区域 | 写入 action | 字段 |
| --- | --- | --- |
| `schema` | `explore_schema` | `selected_fields`, `explore_plan`, `selected_guides`, `query_guide_content`, `schema_detail` |
| `functions` | `explore_functions` | `selected_functions`, `explore_plan`, `func_docs` |
| `knowledge` | `explore_base_knowledge` | `selected_knowledge_ids`, `summary`, `knowledge_content` |
| `mcp` | `explore_mcp` | `selected_tools`, `explore_plan`, `tool_detail`, `catalog` |
| `recent_generated_images` | `generate_and_execute` | `images` |
| `selected_images` | `select_images` / 用户上传图片 | `images`（每项为 `{"path", "reason"}`） |

`recent_generated_images` 区域保存最近一次代码执行生成的图片列表（本地图片通常只存文件名，如 `xxx.png`；本机静态地址或外部 http 图片保留完整 URL）：每次 `generate_and_execute` 执行完成后**覆盖更新**，会经 `blackboard_to_text` 渲染进 `## Blackboard` 提示词段喂给 LLM，前端 Blackboard 弹窗也从该区域读取展示。新写入一律使用键名 `recent_generated_images`；读取时兼容历史持久化数据中的旧拼写键 `rencent_generated_images`（以及更早的 `images`）作为回退，避免旧历史中已生成的图片丢失。

`selected_images` 区域由 `select_images` action 写入，每项为 `{"path": "...", "reason": "..."}`：`path` 是本地 `tmp_imgs` 文件名或完整 `http(s)` 图片链接，`reason` 是一句话选中原因。每次 `select_images` 执行后**整体覆盖**该区域；`images: []` 会清空。用户上传的图片不通过 `select_images`，而是在请求摄取时**追加合并**进该区域（`reason` 为 `"user uploaded image"`，按 `path` 去重，不覆盖已有项）。该区域同样会渲染进 `## Blackboard`，并且其中的图片会排在上一次代码执行生成的 `images` 之后提交给支持多模态的模型。

两个图片区域包含的格式一致，LLM 图片提交逻辑均兼容：

- `xxx.png` / `./tmp_imgs/xxx.png`：从本地 `tmp_imgs/` 读取并转为 base64 data URL。
- `http://127.0.0.1:8008/tmp_imgs/xxx.png`：识别为本机静态图，同样读取本地文件转 base64。
- 外部 `http(s)://...`：原样作为 `image_url` 提交，依赖模型服务端能访问该 URL。
- `data:image/...`：直接透传。
- 文件不存在、非图片或超过 20MB 的图片会被跳过，重复图片会去重。

图片仅在当前模型 `supports_images=true` 且请求 `meta.use_images` 未关闭时提交。提交时用户消息为多模态内容数组，每张图片前会附带文件名标签：

```json
{
  "role": "user",
  "content": [
    {"type": "text", "text": "## Blackboard ..."},
    {"type": "text", "text": "Image filename: xxx.png"},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
  ]
}
```

相关实现：`utils/blackboard.py` 保存图片列表，`agent/utils/llm_access/image_input.py` 负责格式解析与内容组装，`agent/tools/copilot/utils/call_llm_test.py` 负责判断模型能力/开关并提交请求。

blackboard 由 `utils/blackboard.py` 维护：

- `update_blackboard()`：explore / `select_images` 动作完成后写入对应区域
- `update_code_images()`：`generate_and_execute` 执行完成后覆盖写入 `recent_generated_images` 区域
- `normalize_selected_images()`：把 `select_images` 的输入规范为 `{"path", "reason"}` 列表并去重
- `utils/image_ingest.py` 的 `ingest_uploaded_images()`：请求摄取时把 user 条目 `uploaded` 中的 base64 图片保存为 `upload_<8位小写字母>.png` 并**追加合并**进 `selected_images` 区域
- `blackboard_input_images()`：按“`images` 在前、`selected_images` 在后”合并出提交给 LLM 的图片列表并去重
- `replace_blackboard()`：保证 history 中只有一个 blackboard 条目，并固定在第一个位置
- `get_blackboard()`：从完整 history 读取
- `blackboard_section()`：渲染为 `## Blackboard` 提示词段（含 `images` / `selected_images` 区域）

## 通用字段

| 字段 | 说明 |
| --- | --- |
| `role` | `user`、`assistant` 或 `system`（仅 blackboard） |
| `type` | 条目类型：`question` / `choice` / `response` / `input` / `think` / `action_decision` / `act` / `observe` / `document` / `blackboard` |
| `content` | `think`、`action_decision`、`observe`、用户输入和 `document` 的载荷 |
| `regions` | 仅 `type:"blackboard"` 使用，包含 `schema` / `functions` / `knowledge` / `mcp` / `recent_generated_images` / `selected_images` 六个区域 |
| `action` | 仅 `type:"act"` 使用，表示具体动作名 |
| `text` | 前端交互类动作的展示文本 |
| `images` | 仅 `type:"act"` 且 `action:"generate_and_execute"` 使用，本次执行生成的图片文件名列表（本地图片仅存文件名，前端拼 `/tmp_imgs/` 展示；不喂给 LLM） |
| `selected_images` | 仅 `type:"act"` 且 `action:"select_images"` 使用，选中的图片列表，每项为 `{"path", "reason"}`（同时写入 blackboard 的 `selected_images` 区域） |
| `uploaded` | 仅 `user` 条目使用，用户随消息上传的图片。请求体中为 `[{"name": "a.png", "data": "data:image/png;base64,..."}]`；被后端摄取后改写为已保存的文件名列表 `["upload_xxxxxxxx.png"]`（同时合并进 blackboard 的 `selected_images` 区域） |

## 用户输入

用户原始问题：

```json
{"role":"user","type":"question","content":"..."}
```

用户后续反馈：

```json
{"role":"user","type":"choice","content":"用户选择的选项"}
{"role":"user","type":"response","content":"用户对提问的回答"}
{"role":"user","type":"input","content":"用户补充的输入"}
```

### 上传图片

用户在提问时附带的图片写入 `question` 条目的 `uploaded` 字段（无上传时不写该字段）。前端发送时是 base64 data URL 数组，后端摄取后变成文件名列表：

```json
// 前端发送（随 JSON 请求体）
{"role":"user","type":"question","content":"分析这些图片","uploaded":[
  {"name":"cat.jpg","data":"data:image/jpeg;base64,..."}
]}

// 后端摄取/持久化后
{"role":"user","type":"question","content":"分析这些图片","uploaded":["upload_abcd1234.png"]}
```

保存规则：写入 `tmp_imgs/upload_<8位小写字母>.png`，扩展名与生成图片一致，进行格式归一（非 `RGB`/`RGBA` 会转换）。后端按请求卡控：单个请求最多处理 10 张图片、原始 base64 总量不超过 50MB（`utils/image_ingest.py` 的 `MAX_IMAGES_PER_REQUEST` / `MAX_TOTAL_IMAGE_BYTES`），超出预算的项被静默丢弃（仅在服务端打印警告，前端不会收到错误）；不变式是磁盘文件名。

摄取逻辑见 `utils/image_ingest.py`：

- `ingest_uploaded_images(history)`：遍历 user 条目的 `uploaded`，把 base64 项解码保存，改写为文件名列表，并把新增文件名合并进 blackboard 的 `selected_images`（每项 `{"path", "reason": "user uploaded image"}`，按 `path` 去重）。
- 幂等：`uploaded` 已经是文件名字符串时不再处理、不重复合并。
- 单项限制 20MB；解码或保存失败的项会被跳过。

## think

LLM 输出的 JSON 对象，格式为 `{"description": "...", "todo": [...]}`。

```json
{"role":"assistant","type":"think","content":{"description":"...","todo":["..."]}}
```

## action

LLM 输出的 JSON 对象，支持单 action 或多 action。Explore 类（explore_schema/functions/base_knowledge/mcp）与 `select_images` 可批量；用户交互类（ask_question/ask_choice/summary_and_pause/attempt_completion）可批量，summary_and_pause/attempt_completion 必须在最后。两类不可混排。

单 action 格式 `{"action": "...", ...}`：

```json
{"role":"assistant","type":"action_decision","content":{"action":"explore_schema","keyword":"..."}}
```

多 action 格式 `{"actions": [{...}, ...]}`：

```json
{"role":"assistant","type":"action_decision","content":{"actions":[{"action":"explore_schema"},{"action":"explore_functions"}]}}
```

各 action 可能携带的字段及生效条件：

| 字段 | 适用 action | 必填条件 | 省略/为空时的行为 |
| --- | --- | --- | --- |
| `action` | 全部 | 单动作格式必填，与 `actions` 二选一 | 缺少 `actions` 时决策无效 |
| `actions` | 全部 | 多动作格式必填，与 `action` 二选一 | 与 `action` 同时出现时优先使用 `actions` |
| `keyword` | explore_schema / explore_functions / explore_base_knowledge / explore_mcp | 可选 | 不附加关注提示，仍检索全部内容 |
| ~~`funcs`~~ | generate_and_execute | 已移除 | 函数名统一从 blackboard 的 `functions.selected_functions` 读取 |
| `research_guide` | generate_and_execute | 可选 | 为空，不提供额外研究提示 |
| `text` | ask_question / ask_choice / summary_and_pause / attempt_completion | 前端交互必填 | 缺少时前端无可展示/提问的内容 |
| `choices` | ask_choice | ask_choice 必填（至少一项） | 其他 action 中无效；ask_choice 缺失时用户无可选项 |
| `title` | generate_document | 可选 | 由文档生成器自动生成标题 |
| `query` | web_search | 建议必填 | 为空时回退使用当前完整上下文作为查询词 |
| `max_results` | web_search | 可选 | 默认 10，超过 50 按 50 处理 |
| `urls` | fetch_webpage | 建议必填 | URL 数组（1-10 个），并行抓取；为空时回退到单个 `url`，再无则用当前完整上下文 |
| `url` | fetch_webpage | 兼容字段 | 单个 URL 字符串；仅在 `urls` 为空时使用 |
| `max_length` | fetch_webpage | 可选 | 每页默认 10000，超过 50000 按 50000 处理 |
| `server` | exe_mcp | 单工具格式必填，与 `tool` 搭配 | 使用 `tools` 批量格式时忽略 |
| `tool` | exe_mcp | 单工具格式必填，与 `server` 搭配 | 使用 `tools` 批量格式时忽略 |
| `params` | exe_mcp | 可选 | 默认 `{}` |
| `tools` | exe_mcp | 批量格式必填 | 为空时回退到 `server` / `tool` 单工具格式 |
| `images` | select_images | 必填（可为空数组） | 为空数组时清空 `selected_images` 区域；每项需包含 `path`，`reason` 可为空 |
| `selected_images` | select_images | 可选回退字段 | 仅当 `images` 缺失（`null`/未传）时作为其回退读取；两者都缺失或不是数组时报错 `select_images requires an images array` |

## act

`type:"act"` 是动作执行结果。explore_* 条目只保存参数、计划和选中项；完整搜索结果保存在 blackboard，不写入 act 条目。

### explore_schema

```json
{"role":"assistant","type":"act","action":"explore_schema",
 "selected_fields":{"table1":["col1","col2"],"table2":[]},
 "explore_plan":"...",
 "selected_guides":[1,3,7]}
```

完整 `schema_detail` 与 `query_guide_content` 保存在 `blackboard.regions.schema`，不写入 act 条目。

### explore_base_knowledge

```json
{"role":"assistant","type":"act","action":"explore_base_knowledge",
 "selected_knowledge_ids":[1,3,7],
 "summary":"The user's question relates to..."}
```

完整 `knowledge_content` 保存在 `blackboard.regions.knowledge`。

### explore_functions

```json
{"role":"assistant","type":"act","action":"explore_functions",
 "selected_functions":["exe_sql","load_data"],"explore_plan":"..."}
```

完整 `func_docs` 保存在 `blackboard.regions.functions`。

### select_images

```json
{"role":"assistant","type":"act","action":"select_images",
 "selected_images":[
   {"path":"xxx.png","reason":"一句话选中原因"},
   {"path":"https://example.com/chart.png","reason":"一句话选中原因"}
 ]}
```

`path` 为本地 `tmp_imgs` 图片文件名或完整 `http(s)` 链接，`reason` 为一句话选中原因。完整列表同时保存在 `blackboard.regions.selected_images`，重复执行会整体覆盖；上下文格式为每行 `[ACT select_images] {path}: {reason}`。

### generate_and_execute — 成功

```json
{"role":"assistant","type":"act","action":"generate_and_execute",
 "code":"...","result":"...","images":["xxx.png"]}
```

### generate_and_execute — 失败

```json
{"role":"assistant","type":"act","action":"generate_and_execute",
  "error":"[runtime_error] ...","error_kind":"runtime_error","code":"...","result":"...","images":["xxx.png"]}
```

失败时 `error` 必填（带 `[error_kind]` 前缀），并附结构化 `error_kind` 字段（沙箱：`policy_violation` / `syntax_error` / `timeout` / `resource_limit` / `no_func` / `runtime_error` / `environment_error` / `job_error` / `config_error`；生成层：`code_format_error`），供下一步 LLM 读取失败类型；`code` / `result` 在存在时保留。`images` 为本轮执行过程中生成的图片文件名列表（去重后，本地图片仅存文件名，外部 http 图片保留完整 URL），无论成功失败，只要生成过图片就保留；仅用于前端展示，不进入 LLM 上下文。

### generate_document

```json
{"role":"assistant","type":"act","action":"generate_document",
 "title":"报告标题","file_name":"文件名",
 "full_text":"文档全文",
 "download_url_md":"...","download_url_docx":"...","download_url_pdf":"..."}
```

`title` 来自 action 决策的 `title`；`file_name` 为生成文件的主名；三个 `download_url_*` 为对应格式的下载地址。

### web_search

```json
{"role":"assistant","type":"act","action":"web_search",
 "search_result":"格式化后的 markdown 搜索结果字符串",
 "query":"..."}
```

成功时 `search_result` 为格式化后的 markdown 搜索结果字符串；搜索失败（`search_web` 返回 error）时该条目的 `search_result` 写入的是结果字典（形如 `{"error": "..."}`），并非字符串。

上下文格式：

```
[ACT web_search] search_result:
{search_result}
[ACT web_search] query: {query}
```

### explore_mcp

```json
{"role":"assistant","type":"act","action":"explore_mcp",
 "selected_tools":[{"server":"calculator","name":"calculate"},...],
 "explore_plan":"..."}
```

完整 `tool_detail` / `catalog` 保存在 `blackboard.regions.mcp`。

上下文格式：

```
[ACT explore_mcp] selected_tools: [{"server":"calculator","name":"calculate"},...]
[ACT explore_mcp] explore_plan:
{plan}
```

### exe_mcp

```json
{"role":"assistant","type":"act","action":"exe_mcp",
 "results":[{"server":"server_name","tool":"tool_name","result":{...}},...],
 "display_content":"汇总展示文本"}
```

上下文格式：

```
[ACT exe_mcp] {server}/{tool} result:
{result_json}
```

`results`、`display_content`、`error` 三个字段仅在非空时写入条目：成功时没有 `error` 键（不是 `error:null`）；单次调用失败时 `results` 中对应项带 `error`，整体失败（如未提供可用工具）时才会出现顶层 `error`。

### fetch_webpage

并行抓取 `urls` 中每个 URL 的正文，**每个 URL 生成一条 act 条目**（按输入顺序）：

```json
{"role":"assistant","type":"act","action":"fetch_webpage",
 "url":"...","page_content":"格式化后的 markdown 页面内容字符串"}
```

抓取失败的页面 `page_content` 为 `[Error] <原因>`。

上下文格式（逐条渲染）：

```
[ACT fetch_webpage] page_content:
{page_content}
[ACT fetch_webpage] url: {url}
```

### 纯前端执行

`ask_question` / `ask_choice` / `summary_and_pause` / `attempt_completion`

```json
{"role":"assistant","type":"act","action":"ask_question","text":"..."}
{"role":"assistant","type":"act","action":"ask_choice","text":"...","choices":["A","B"]}
```

下表状态标记只在**从日志重建历史**（`data_access/observe_log.py`）时补充；网页前端本地渲染这类动作通常不调用 `/api/act/stream/`，而 API 调用方直接调用 `/api/act/stream/` 时 `agent/act.py` 也会写出一条独立 `act` 条目，但**不带**这些状态标记：

| 标记 | 适用 action |
| --- | --- |
| `needs_user_input: true` | ask_question / ask_choice |
| `choices: []` | ask_choice |
| `paused: true` | summary_and_pause |
| `completed: true` | attempt_completion |

> 实时流程中，前端执行类动作通常只出现在 `action_decision.content` 里（带 `action` 与 `text`），不一定单独产生 `type:"act"` 条目；由日志重建时才会补成带上述状态标记的 `act` 条目。重建仅针对决策里带非空 `text` 的前端交互动作——重建侧的 `FRONTEND_ACTIONS`（`data_access/observe_log.py`）除 ask_question / ask_choice / summary_and_pause / attempt_completion 外还包含 `generate_document`；`generate_document` 决策通常携带 `title` 而非 `text`，因此一般不会为它补出 `act` 条目，但一旦其决策带非空 `text`，重建同样会补出并置 `completed: true`（所以 `completed: true` 并非只由 attempt_completion 触发，只是实践中几乎总是来自 attempt_completion）。

## observe

LLM 输出的 JSON 对象，格式为 `{"description": "...", "todo": [...]}`。

```json
{"role":"assistant","type":"observe","content":{"description":"...","todo":["..."]}}
```

## document

文档生成接口产出的完整文档内容，用于历史重建：

```json
{"role":"assistant","type":"document","content":"...markdown..."}
```

## 上下文渲染

送给 LLM 前，由 `utils/front_utils.py` 的 `history_to_text` 将裁剪后的普通条目转成纯文本。遇到 `type:"blackboard"` 时直接跳过，不进入上下文文本。

| 条目 | 渲染结果 |
| --- | --- |
| `user/question` | `Q: {content}{uploaded_suffix}` |
| `user/choice` | `User chose: {content}{uploaded_suffix}` |
| `user/response` | `User response: {content}{uploaded_suffix}` |
| `user/input` | `User: {content}{uploaded_suffix}` |
| `think` | `[THINK] content:\n{content}` |
| `action_decision` | `[ACTION] content:\n{content}` |
| `act` | `[ACT {action}] ...` 各字段按行输出 |
| `observe` | `[OBSERVE] content:\n{content}` |
| `blackboard` | 跳过，由 blackboard_section 单独渲染 |

`content` 为对象时使用 `json.dumps(..., ensure_ascii=False)` 序列化。

`uploaded_suffix`：当 user 条目带 `uploaded` 时，在该行后追加一行 `\nUploaded images: a.png, b.png`。仅取文件名（字符串项，或对象项的 `path`/`filename`/`name`），因此 LLM 能看到用户上传的文件名列表。

`generate_and_execute` 条目的 `images` 字段不会被 `history_to_text` 渲染，因此不会进入任何 LLM 阶段。失败条目（带 `error`）的 `result`（执行中途已产出的部分输出）会被渲染为 `[ACT generate_and_execute] result (partial; execution failed afterwards):`，使下一步 LLM 同时看到错误与部分结果（无 `result` 时只渲染 `error`）。

## blackboard 渲染

`utils/blackboard.py` 的 `blackboard_section(conversation_history)` 从完整 history 中读取 blackboard，渲染成独立的 `## Blackboard` 段：

```text
## Blackboard

### DB
note: Database schema gathered by `explore_schema`: `selected_fields` lists relevant tables/columns, with schema details and query guidance. Re-running `explore_schema` overwrites this region.
selected_fields:
{"table": ["col1"]}
explore_plan:
...
selected_guides:
[1, 3]
query_guide_content:
...
schema_detail:
...

### FUNC
note: Function catalog gathered by `explore_functions`: `selected_functions` lists callable function names and `func_docs` contains their documentation. Re-running `explore_functions` overwrites this region.
selected_functions:
["exe_sql"]
explore_plan:
...
func_docs:
...

### KNOWLEDGE
note: Business domain knowledge gathered by `explore_base_knowledge`: selected knowledge IDs, a summary, and the full content. Re-running `explore_base_knowledge` overwrites this region.
selected_knowledge_ids:
[1, 2]
summary:
...
knowledge_content:
...

### MCP
note: External MCP tools gathered by `explore_mcp`: selected tools, tool details, and the catalog; call them with `exe_mcp`. Re-running `explore_mcp` overwrites this region.
selected_tools:
[{"server": "calculator", "name": "calculate"}]
explore_plan:
...
tool_detail:
...
catalog:
...

### RECENT_GENERATED_IMAGES
note: Images generated by the most recent code execution. They are attached automatically to the next LLM call.
images:
["xxx.png", "http://.../yyy.png"]

### SELECTED IMAGES
note: Images explicitly kept by `select_images` or uploaded by the user, each with a path and a reason. They stay attached to every later LLM call until the region is overwritten.
images:
[{"path": "xxx.png", "reason": "一句话选中原因"}, {"path": "upload_abcd1234.png", "reason": "user uploaded image"}]
```

`recent_generated_images` / `selected_images` 区域分别渲染为 `### RECENT_GENERATED_IMAGES` / `### SELECTED IMAGES` 段（字段 `images` 均为 JSON），并各自带一行 `note` 说明其含义与附带规则，随 `## Blackboard` 一起注入所有 LLM 阶段。聊天记录 `act` 条目里的 `images` 字段仍只用于前端展示，不进入 `history_to_text`。除文本注入外，图片还会按上文的规则在模型支持且 `use_images` 开启时作为 `image_url` 内容提交，顺序为 `recent_generated_images` 在前、`selected_images` 在后。

该段会注入到所有 LLM 阶段：Think、Action、Observe、Act explore_*、generate_and_execute、文档生成。

## 裁剪规则

`utils/context_trim.py` 的 `trim_conversation_history` 从数组末尾向前按类别计数保留，`user` 条目始终保留。`trimmed_context` 即普通条目的裁剪结果。

- `blackboard` 条目**直接跳过**，不进入 `trimmed_context`；它始终从完整 `conversation_history` 单独读取。
- 所有 LLM 阶段使用 `prepare_trimmed_context` 重新裁剪，而不是直接读取数据库里的 `trimmed_context` 列。

| 类别 | 保留条数 |
| --- | --- |
| think（`think` 条目） | 3 |
| action（`action_decision` 条目） | 3 |
| generate_and_execute 含 `error`（`act_error`） | 1 |
| generate_and_execute 含 `result` / `exec_ok`（`act_result`） | 999（永久） |
| generate_and_execute 含 `code`（`act_code`，仅「有代码但无 `result`/`error`」的条目） | 1 |
| explore_schema | 3 |
| explore_functions | 3 |
| explore_base_knowledge | 3 |
| explore_mcp | 3 |
| select_images | 3 |
| web_search | 3 |
| fetch_webpage | 5 |
| exe_mcp | 999（永久） |
| ask_question / ask_choice / summary_and_pause / attempt_completion | 999（永久） |
| generate_document | 1 |
| observe_<action>（带 action 的 observe，已列出的动作：explore_schema / explore_functions / explore_base_knowledge / generate_and_execute / ask_question / ask_choice / summary_and_pause / attempt_completion） | 3 |
| observe（无 action，或 action 未在上行列出，归入 `observe_default`） | 5 |
| 未匹配类别 | 999（永久） |
| blackboard | 不参与裁剪（不进入 trimmed_context） |

> `generate_and_execute` 条目的分类顺序固定：先判 `error`（命中即 `act_error`，保留 1），其次判 `result` / `exec_ok`（命中即 `act_result`，保留 999，永久），最后才判 `code`（`act_code`，保留 1，只命中「有 code 但无 result/error」的条目）。落库的成功/失败条目都带 `result` 或 `error`，因此大多落入 `act_result` 被永久保留，`act_code`（保留 1）实际只约束「只有代码、没有执行结果」的条目；对更早的含 `code` 条目，裁剪不会丢弃整条，而是仅剥离其 `code` 字段（`_strip_generated_code`），条目本身和执行结果保留。

## 各阶段使用方式

每个 LLM 阶段同时接收两部分：`## Context`（裁剪后的普通条目）和 `## Blackboard`（完整搜索内容）。

| 阶段 | 上下文 | blackboard |
| --- | --- | --- |
| Think | `history_to_text(prepare_trimmed_context(...))` | `blackboard_section(conversation_history)` |
| Action | 同上 | 同上 |
| Observe | 同上 | 同上 |
| Act explore_schema / explore_functions / explore_base_knowledge / explore_mcp | 同上 | 同上 |
| Act select_images | 同上 | 同上 |
| Act generate_and_execute | 同上 | 同上 |
| 文档生成 / YAML 生成 | 同上（先裁剪） | 同上 |

文档生成虽然使用完整 `conversation_history` 作为输入，但在拼接 prompt 前会先调用 `prepare_trimmed_context`，因此同样只使用裁剪后的上下文。

## 存储

完整历史与裁剪后上下文保存在 `observe_session_log` 表：

```sql
conversation_history LONGTEXT  -- 完整历史（JSON 数组，含 blackboard）
trimmed_context      LONGTEXT  -- 裁剪后的普通上下文（JSON 数组，不含 blackboard）
```
