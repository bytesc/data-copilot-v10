# conversation_history 结构定义

`conversation_history` 是一个 JSON 数组，按发生顺序记录用户输入与 Agent 各阶段输出。数组元素统一为对象，基础字段为 `role`、`type`，其余字段随类型不同而不同。

逻辑上分为两部分：

- **blackboard 条目**：完整搜索结果，固定在数组第一个位置，包含 DB schema、函数文档、业务知识、MCP 工具详情，以及最近一次代码执行生成的图片列表。
- **普通条目**：用户输入、`think`、`action_decision`、`act` 元数据、`observe` 等。

数据库中的两份数据：

- `conversation_history`：完整历史，包含 blackboard。
- `trimmed_context`：按保留策略裁剪后的普通条目，**不包含 blackboard**；实际送给 LLM 的上下文文本由它经 `history_to_text` 生成。

blackboard 不进入 `trimmed_context`，而是由 `utils/blackboard.py` 单独提取成 `## Blackboard` 段，注入所有 LLM 阶段。

基础形态：

```json
[
  {"role": "system", "type": "blackboard", "regions": {"schema": {}, "functions": {}, "knowledge": {}, "mcp": {}, "images": {}}},
  {"role": "user", "type": "question", "content": "..."},
  {"role": "assistant", "type": "think", "content": {"description": "...", "todo": ["..."]}},
  {"role": "assistant", "type": "action_decision", "content": {"action": "..."}},
  {"role": "assistant", "type": "act", "action": "...", "...": "..."},
  {"role": "assistant", "type": "observe", "content": {"description": "...", "todo": ["..."]}}
]
```

## 完整示例

以下把所有条目类型和 `action_decision` 的可选字段放在同一个数组中，仅用于展示字段全集。真实记录中：

- 每个 `action_decision` 只携带当前 action 对应的字段，不会同时出现所有可选字段。
- 同一决策使用多动作时，用 `{"actions":[{...}, ...]}` 代替 `action`。
- 前端交互类动作在实时流程中通常只出现在 `action_decision.content`；由日志重建时才会补成独立的 `act` 条目并带状态标记。

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
        "knowledge_content": "知识内容",
        "summary": "摘要"
      },
      "mcp": {
        "selected_tools": [],
        "explore_plan": "探索计划",
        "tool_detail": "工具详情",
        "catalog": "工具目录"
      },
      "images": {
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
    "action": "output_text",
    "text": "输出文本"
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

blackboard 是完整 history 的第一个元素，保存 explore 类动作选中的完整搜索结果，以及最近一次代码执行生成的图片列表。各 explore action 只把参数/计划/选中项写入对应的 `act` 条目，完整内容统一写入 blackboard 的对应区域。

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
      "knowledge_content": "...",
      "summary": "..."
    },
    "mcp": {
      "selected_tools": [{"server": "calculator", "name": "calculate"}],
      "explore_plan": "...",
      "tool_detail": "...",
      "catalog": "..."
    },
    "images": {
      "images": ["xxx.png"]
    }
  }
}
```

| 区域 | 写入 action | 字段 |
| --- | --- | --- |
| `schema` | `explore_schema` | `selected_fields`, `explore_plan`, `selected_guides`, `query_guide_content`, `schema_detail` |
| `functions` | `explore_functions` | `selected_functions`, `explore_plan`, `func_docs` |
| `knowledge` | `explore_base_knowledge` | `selected_knowledge_ids`, `knowledge_content`, `summary` |
| `mcp` | `explore_mcp` | `selected_tools`, `explore_plan`, `tool_detail`, `catalog` |
| `images` | `generate_and_execute` | `images` |

`images` 区域保存最近一次代码执行生成的图片文件名列表（本地图片仅存文件名，如 `xxx.png`；外部 http 图片保留完整 URL）：每次 `generate_and_execute` 执行完成后**覆盖更新**，会经 `blackboard_to_text` 渲染进 `## Blackboard` 提示词段喂给 LLM，前端 Blackboard 弹窗也从该区域读取展示。

blackboard 由 `utils/blackboard.py` 维护：

- `update_blackboard()`：explore 动作完成后写入对应区域
- `update_code_images()`：`generate_and_execute` 执行完成后覆盖写入 `images` 区域
- `replace_blackboard()`：保证 history 中只有一个 blackboard 条目，并固定在第一个位置
- `get_blackboard()`：从完整 history 读取
- `blackboard_section()`：渲染为 `## Blackboard` 提示词段（含 `images` 区域）

## 通用字段

| 字段 | 说明 |
| --- | --- |
| `role` | `user`、`assistant` 或 `system`（仅 blackboard） |
| `type` | 条目类型：`question` / `choice` / `response` / `input` / `think` / `action_decision` / `act` / `observe` / `document` / `blackboard` |
| `content` | `think`、`action_decision`、`observe`、用户输入和 `document` 的载荷 |
| `regions` | 仅 `type:"blackboard"` 使用，包含 `schema` / `functions` / `knowledge` / `mcp` / `images` 五个区域 |
| `action` | 仅 `type:"act"` 使用，表示具体动作名 |
| `text` | 前端交互类动作的展示文本 |
| `images` | 仅 `type:"act"` 且 `action:"generate_and_execute"` 使用，本次执行生成的图片文件名列表（本地图片仅存文件名，前端拼 `/tmp_imgs/` 展示；不喂给 LLM） |

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

## think

LLM 输出的 JSON 对象，格式为 `{"description": "...", "todo": [...]}`。

```json
{"role":"assistant","type":"think","content":{"description":"...","todo":["..."]}}
```

## action

LLM 输出的 JSON 对象，支持单 action 或多 action。Explore 类（explore_schema/functions/base_knowledge）可批量；用户交互类（output_text/ask_question/ask_choice/summary_and_pause/attempt_completion）可批量，summary_and_pause/attempt_completion 必须在最后。两类不可混排。

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
| `text` | output_text / ask_question / ask_choice / summary_and_pause / attempt_completion | 前端交互必填 | 缺少时前端无可展示/提问的内容 |
| `choices` | ask_choice | ask_choice 必填（至少一项） | 其他 action 中无效；ask_choice 缺失时用户无可选项 |
| `title` | generate_document | 可选 | 由文档生成器自动生成标题 |
| `query` | web_search | 建议必填 | 为空时回退使用当前完整上下文作为查询词 |
| `max_results` | web_search | 可选 | 默认 10，超过 50 按 50 处理 |
| `url` | fetch_webpage | 建议必填 | 为空时回退使用当前完整上下文作为地址 |
| `max_length` | fetch_webpage | 可选 | 默认 10000，超过 50000 按 50000 处理 |
| `server` | exe_mcp | 单工具格式必填，与 `tool` 搭配 | 使用 `tools` 批量格式时忽略 |
| `tool` | exe_mcp | 单工具格式必填，与 `server` 搭配 | 使用 `tools` 批量格式时忽略 |
| `params` | exe_mcp | 可选 | 默认 `{}` |
| `tools` | exe_mcp | 批量格式必填 | 为空时回退到 `server` / `tool` 单工具格式 |

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

### generate_and_execute — 成功

```json
{"role":"assistant","type":"act","action":"generate_and_execute",
 "code":"...","result":"...","images":["xxx.png"]}
```

### generate_and_execute — 失败

```json
{"role":"assistant","type":"act","action":"generate_and_execute",
 "error":"...","code":"...","result":"...","images":["xxx.png"]}
```

失败时 `error` 必填，`code` / `result` 在存在时保留。`images` 为本轮执行过程中生成的图片文件名列表（去重后，本地图片仅存文件名，外部 http 图片保留完整 URL），无论成功失败，只要生成过图片就保留；仅用于前端展示，不进入 LLM 上下文。

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
 "display_content":"汇总展示文本",
 "error":null}
```

上下文格式：

```
[ACT exe_mcp] {server}/{tool} result:
{result_json}
```

单次调用失败时 `results` 中对应项带 `error`；整体失败时使用顶层 `error`。

### fetch_webpage

```json
{"role":"assistant","type":"act","action":"fetch_webpage",
 "url":"...","page_content":"格式化后的 markdown 页面内容字符串"}
```

上下文格式：

```
[ACT fetch_webpage] page_content:
{page_content}
[ACT fetch_webpage] url: {url}
```

### 纯前端执行

`output_text` / `ask_question` / `ask_choice` / `summary_and_pause` / `attempt_completion`

```json
{"role":"assistant","type":"act","action":"output_text","text":"..."}
{"role":"assistant","type":"act","action":"ask_choice","text":"...","choices":["A","B"]}
```

从日志重建历史时，会额外补充状态标记：

| 标记 | 适用 action |
| --- | --- |
| `needs_user_input: true` | ask_question / ask_choice |
| `choices: []` | ask_choice |
| `paused: true` | summary_and_pause |
| `completed: true` | attempt_completion / generate_document |

> 实时流程中，前端执行类动作通常只出现在 `action_decision.content` 里（带 `action` 与 `text`），不一定单独产生 `type:"act"` 条目；由日志重建时才会补成上述 `act` 条目。

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
| `user/question` | `Q: {content}` |
| `user/choice` | `User chose: {content}` |
| `user/response` | `User response: {content}` |
| `user/input` | `User: {content}` |
| `think` | `[THINK] content:\n{content}` |
| `action_decision` | `[ACTION] content:\n{content}` |
| `act` | `[ACT {action}] ...` 各字段按行输出 |
| `observe` | `[OBSERVE] content:\n{content}` |
| `blackboard` | 跳过，由 blackboard_section 单独渲染 |

`content` 为对象时使用 `json.dumps(..., ensure_ascii=False)` 序列化。

`generate_and_execute` 条目的 `images` 字段不会被 `history_to_text` 渲染，因此不会进入任何 LLM 阶段。

## blackboard 渲染

`utils/blackboard.py` 的 `blackboard_section(conversation_history)` 从完整 history 中读取 blackboard，渲染成独立的 `## Blackboard` 段：

```text
## Blackboard

### DB
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
selected_functions:
["exe_sql"]
explore_plan:
...
func_docs:
...

### KNOWLEDGE
selected_knowledge_ids:
[1, 2]
knowledge_content:
...
summary:
...

### MCP
selected_tools:
[{"server": "calculator", "name": "calculate"}]
explore_plan:
...
tool_detail:
...
catalog:
...

### IMAGES
images:
["xxx.png", "http://.../yyy.png"]
```

`images` 区域渲染为 `### IMAGES` 段（字段 `images` 为 JSON 数组），随 `## Blackboard` 一起注入所有 LLM 阶段。聊天记录 `act` 条目里的 `images` 字段仍只用于前端展示，不进入 `history_to_text`。

该段会注入到所有 LLM 阶段：Think、Action、Observe、Act explore_*、generate_and_execute、文档生成。

## 裁剪规则

`utils/context_trim.py` 的 `trim_conversation_history` 从数组末尾向前按类别计数保留，`user` 条目始终保留。`trimmed_context` 即普通条目的裁剪结果。

- `blackboard` 条目**直接跳过**，不进入 `trimmed_context`；它始终从完整 `conversation_history` 单独读取。
- 所有 LLM 阶段使用 `prepare_trimmed_context` 重新裁剪，而不是直接读取数据库里的 `trimmed_context` 列。

| 类别 | 保留条数 |
| --- | --- |
| think | 3 |
| action_decision | 3 |
| generate_and_execute 代码 | 1 |
| generate_and_execute 失败 | 1 |
| generate_and_execute 结果 | 999（永久） |
| explore_schema | 3 |
| explore_functions | 3 |
| explore_base_knowledge | 3 |
| explore_mcp | 3 |
| web_search / fetch_webpage | 3 |
| exe_mcp | 999（永久） |
| output_text / ask_question / ask_choice / summary_and_pause / attempt_completion | 999（永久） |
| generate_document | 1 |
| observe（默认） | 5 |
| 未匹配类别 | 999（永久） |
| blackboard | 不参与裁剪（不进入 trimmed_context） |

## 各阶段使用方式

每个 LLM 阶段同时接收两部分：`## Context`（裁剪后的普通条目）和 `## Blackboard`（完整搜索内容）。

| 阶段 | 上下文 | blackboard |
| --- | --- | --- |
| Think | `history_to_text(prepare_trimmed_context(...))` | `blackboard_section(conversation_history)` |
| Action | 同上 | 同上 |
| Observe | 同上 | 同上 |
| Act explore_schema / explore_functions / explore_base_knowledge / explore_mcp | 同上 | 同上 |
| Act generate_and_execute | 同上 | 同上 |
| 文档生成 / YAML 生成 | 同上（先裁剪） | 同上 |

文档生成虽然使用完整 `conversation_history` 作为输入，但在拼接 prompt 前会先调用 `prepare_trimmed_context`，因此同样只使用裁剪后的上下文。

## 存储

完整历史与裁剪后上下文保存在 `observe_session_log` 表：

```sql
conversation_history LONGTEXT  -- 完整历史（JSON 数组，含 blackboard）
trimmed_context      LONGTEXT  -- 裁剪后的普通上下文（JSON 数组，不含 blackboard）
```
