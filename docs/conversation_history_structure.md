# conversation_history 结构定义

`conversation_history` 是一个 JSON 数组，按发生顺序记录用户输入与 Agent 各阶段输出。数组元素统一为对象，基础字段为 `role`、`type`，其余字段随类型不同而不同。

- `conversation_history`：完整历史，保存全部条目。
- `trimmed_context`：按保留策略裁剪后的历史，实际送给 LLM 的上下文；结构与本文件完全一致，只是条目数量更少（见文末「裁剪规则」）。

基础形态：

```json
[
  {"role": "user", "type": "question", "content": "..."},
  {"role": "assistant", "type": "think", "content": {"description": "...", "todo": ["..."]}},
  {"role": "assistant", "type": "action_decision", "content": {"action": "..."}},
  {"role": "assistant", "type": "act", "action": "...", "...": "..."},
  {"role": "assistant", "type": "observe", "content": {"description": "...", "todo": ["..."]}}
]
```

## 通用字段

| 字段 | 说明 |
| --- | --- |
| `role` | `user` 或 `assistant` |
| `type` | 条目类型：`question` / `choice` / `response` / `input` / `think` / `action_decision` / `act` / `observe` / `document` |
| `content` | `think`、`action_decision`、`observe`、用户输入和 `document` 的载荷 |
| `action` | 仅 `type:"act"` 使用，表示具体动作名 |
| `text` | 前端交互类动作的展示文本 |

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

各 action 可能携带的字段：

| 字段 | 适用 action |
| --- | --- |
| `keyword` | explore_schema / explore_functions / explore_base_knowledge / explore_mcp |
| `funcs` | generate_and_execute |
| `research_guide` | generate_and_execute |
| `text` | output_text / ask_question / ask_choice / summary_and_pause / attempt_completion |
| `choices` | ask_choice |
| `title` | generate_document |
| `query`、`max_results` | web_search |
| `url`、`max_length` | fetch_webpage |
| `server`、`tool`、`params` | exe_mcp |
| `tools` | exe_mcp（批量调用） |

## act

`type:"act"` 是动作执行结果。除 `explore_schema` 等带详细字段的条目外，都可能带有 `action` 字段。

### explore_schema

```json
{"role":"assistant","type":"act","action":"explore_schema",
 "selected_fields":{"table1":["col1","col2"],"table2":[]},
 "explore_plan":"...","schema_detail":"...",
 "selected_guides":[1,3,7],"query_guide_content":"### Rule: Find companies by topic\n..."}
```

### explore_base_knowledge

```json
{"role":"assistant","type":"act","action":"explore_base_knowledge",
 "selected_knowledge_ids":[1,3,7],"knowledge_content":"### Rule: ...\n...",
 "summary":"The user's question relates to..."}
```

### explore_functions

```json
{"role":"assistant","type":"act","action":"explore_functions",
 "selected_functions":["exe_sql","load_data"],"explore_plan":"...","func_docs":"..."}
```

### generate_and_execute — 成功

```json
{"role":"assistant","type":"act","action":"generate_and_execute",
 "code":"...","result":"..."}
```

### generate_and_execute — 失败

```json
{"role":"assistant","type":"act","action":"generate_and_execute",
 "error":"...","code":"...","result":"..."}
```

失败时 `error` 必填，`code` / `result` 在存在时保留。

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
 "tool_detail":"格式化后的 markdown 选中工具展示",
 "explore_plan":"..."}
```

上下文格式：

```
[ACT explore_mcp] selected_tools: [{"server":"calculator","name":"calculate"},...]
[ACT explore_mcp] explore_plan:
{plan}
[ACT explore_mcp] tool_detail:
{tool_detail}
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

送给 LLM 前，由 `utils/front_utils.py` 的 `history_to_text` 将数组转成纯文本：

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

`content` 为对象时使用 `json.dumps(..., ensure_ascii=False)` 序列化。

## 裁剪规则

`utils/context_trim.py` 的 `trim_conversation_history` 从数组末尾向前按类别计数保留，`user` 条目始终保留。`trimmed_context` 即裁剪结果。

| 类别 | 保留条数 |
| --- | --- |
| think | 3 |
| action_decision | 3 |
| generate_and_execute 代码 | 1 |
| generate_and_execute 失败 | 1 |
| generate_and_execute 结果 | 999（永久） |
| explore_schema / explore_functions / explore_base_knowledge / explore_mcp | 999（永久） |
| web_search / fetch_webpage | 3 |
| exe_mcp | 999（永久） |
| output_text / ask_question / ask_choice / summary_and_pause / attempt_completion | 999（永久） |
| generate_document | 1 |
| observe | 3 |
| 未匹配类别 | 999（永久） |

## 存储

完整历史与裁剪后上下文保存在 `observe_session_log` 表：

```sql
conversation_history LONGTEXT  -- 完整上下文（JSON 数组）
trimmed_context      LONGTEXT  -- 裁剪后的上下文（JSON 数组）
```
