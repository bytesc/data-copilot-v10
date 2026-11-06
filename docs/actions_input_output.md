# Action 输入输出文档

> 文中 API 入参示例展示的是统一请求信封中的 `data` 内容；实际发送到后端的 JSON `POST/PUT/PATCH`
> 请求体必须为 `{"meta": {"model": "...", "reasoning_effort": "...", "style": "...", "use_images": true}, "data": {...}}`。

每个环节记录三项：**输入**（LLM 决策输出的 JSON / API 入参）、**输出**（写入 `conversation_history` 的条目）、**上下文**（`history_to_text` 转换后喂给 LLM 的文本）。

> 除下文列出的上下文外，每个 LLM 阶段还会额外注入独立的 `## Blackboard` 段（`blackboard_section(conversation_history)`），用于提供完整的 DB schema、函数文档、业务知识和 MCP 工具详情。blackboard 不进入 `history_to_text`，详见 `docs/conversation_history_structure.md`。blackboard 的 `images` 区域（最近一次代码执行生成的图片列表）和 `selected_images` 区域（`select_images` 选中的图片及原因）也随该段以文本注入；当模型 `supports_images=true` 且请求 `meta.use_images` 开启时，两处图片会按 `images` 在前、`selected_images` 在后的顺序以 `image_url` 内容数组的形式随请求提交（本地文件/本机静态 URL 转 base64，外部 URL 原样传递，详见 `docs/conversation_history_structure.md`）。

---

## 1. Think

**输入**
```json
{"question": "...", "session_id": "...", "conversation_history": [...]}
```

**输出**
```json
{"role":"assistant","type":"think","content":{"description":"...","todo":["..."]}}
```

**上下文**
```
[THINK] content:
{"description": "...", "todo": ["...", "..."]}
```

---

## 2. Action（通用）

**输入**
```json
{"question": "...", "session_id": "...", "conversation_history": [...], "cycle_index": 0}
```

**输出（单 action）**
```json
{"role":"assistant","type":"action_decision","content":{"action":"...", ...}}
```

**输出（多 action，Explore 类与 select_images 可批量）**
```json
{"role":"assistant","type":"action_decision","content":{"actions":[{"action":"explore_schema"},{"action":"explore_functions"}]}}
```

**输出（多 action，用户交互类可批量，summary_and_pause/attempt_completion 必须在最后）**
```json
{"role":"assistant","type":"action_decision","content":{"actions":[{"action":"output_text","text":"..."},{"action":"ask_question","text":"..."}]}}
```

**上下文**
```
[ACTION] content:
{"action": "...", ...}
```

**可选参数、对应 action 与生效条件**

| 参数 | 可用 action | 必填条件 | 省略/为空时的行为 |
| --- | --- | --- | --- |
| `action` | 全部 | 单动作格式必填，与 `actions` 二选一 | 缺少 `actions` 时决策无效 |
| `actions` | 全部 | 多动作格式必填，与 `action` 二选一 | 与 `action` 同时出现时优先使用 `actions` |
| `keyword` | explore_schema / explore_functions / explore_base_knowledge / explore_mcp | 可选 | 不附加关注提示，不用于过滤数据 |
| ~~`funcs`~~ | generate_and_execute | 已移除 | 函数名统一从 blackboard 的 `functions.selected_functions` 读取 |
| `research_guide` | generate_and_execute | 可选 | 为空，不提供额外研究提示 |
| `text` | output_text / ask_question / ask_choice / summary_and_pause / attempt_completion | 前端交互必填 | 缺少时前端无可展示/提问的内容 |
| `choices` | ask_choice | ask_choice 必填（至少一项） | 其他 action 中无效 |
| `title` | generate_document | 可选 | 由文档生成器自动生成标题 |
| `query` | web_search | 建议必填 | 为空时回退使用当前完整上下文作为查询词 |
| `max_results` | web_search | 可选 | 默认 10，超过 50 按 50 处理 |
| `url` | fetch_webpage | 建议必填 | 为空时回退使用当前完整上下文作为地址 |
| `max_length` | fetch_webpage | 可选 | 默认 10000，超过 50000 按 50000 处理 |
| `server` | exe_mcp | 单工具格式必填，与 `tool` 搭配 | 使用 `tools` 批量格式时忽略 |
| `tool` | exe_mcp | 单工具格式必填，与 `server` 搭配 | 使用 `tools` 批量格式时忽略 |
| `params` | exe_mcp | 可选 | 默认 `{}` |
| `tools` | exe_mcp | 批量格式必填 | 为空时回退到 `server` / `tool` 单工具格式 |
| `images` | select_images | 必填（可为空数组） | 为空数组时清空 `selected_images` 区域；每项为 `{"path", "reason"}` |

后端只保留上述字段（`agent/action.py` 的 `_parse_action_json`），未列出的字段会被丢弃。

---

## 3. explore_schema

**输入**
```json
{"action": "explore_schema", "keyword": "..."}
```
keyword 为可选提示词，传递给 LLM 作为关注重点的提示，不用于过滤数据。

**输出**
```json
{"role":"assistant","type":"act","action":"explore_schema","selected_fields":{...},"explore_plan":"...","selected_guides":[...]}
```

**Blackboard 写入**
```json
{"regions":{"schema":{"selected_fields":{...},"explore_plan":"...","selected_guides":[...],"query_guide_content":"...","schema_detail":"..."}}}
```

**上下文**
```
[ACT explore_schema] selected_fields: {"table1":["col1"],...}
[ACT explore_schema] explore_plan:
{plan}
[ACT explore_schema] selected_guides: [1, 3, 7]
```

完整 `schema_detail` / `query_guide_content` 只保存在 blackboard，并通过 `## Blackboard` 段注入所有 LLM 阶段。

---

## 3.5. explore_base_knowledge

**输入**
```json
{"action": "explore_base_knowledge", "keyword": "..."}
```
keyword 为可选提示词，传递给 LLM 作为关注重点的提示，不用于过滤数据。

**输出**
```json
{"role":"assistant","type":"act","action":"explore_base_knowledge","selected_knowledge_ids":[...],"summary":"..."}
```

**Blackboard 写入**
```json
{"regions":{"knowledge":{"selected_knowledge_ids":[...],"knowledge_content":"...","summary":"..."}}}
```

**上下文**
```
[ACT explore_base_knowledge] selected_knowledge_ids: [1, 3, 7]
[ACT explore_base_knowledge] summary:
{summary}
```

完整 `knowledge_content` 只保存在 blackboard。

---

## 4. explore_functions

**输入**
```json
{"action": "explore_functions", "keyword": "..."}
```
keyword 为可选提示词，传递给 LLM 作为关注重点的提示，不用于过滤数据。

**输出**
```json
{"role":"assistant","type":"act","action":"explore_functions","selected_functions":[...],"explore_plan":"..."}
```

**Blackboard 写入**
```json
{"regions":{"functions":{"selected_functions":[...],"explore_plan":"...","func_docs":"..."}}}
```

**上下文**
```
[ACT explore_functions] selected_functions: ["func1",...]
[ACT explore_functions] explore_plan:
{explore_plan}
```

完整 `func_docs` 只保存在 blackboard。

---

## 4.5. select_images

**输入**
```json
{"action": "select_images", "images": [
  {"path": "xxx.png", "reason": "一句话说明为什么保留这张图"},
  {"path": "https://example.com/chart.png", "reason": "一句话说明为什么保留这张图"}
]}
```

`path` 为本地 `tmp_imgs` 下的图片文件名，或完整的 `http(s)` 图片链接；`reason` 为每个图片的一句话选中原因。该 action 属于 Group 1，可与 `explore_*` 动作在同一次 `actions` 数组中批量执行。重复执行会**整体覆盖** `selected_images` 区域；`images: []` 会清空该区域。当用户需求变化（新范围、新分析目标或纠正）时，应重新运行 `select_images` 更新该区域，而不是保留过期的选中图片。

**输出**
```json
{"role":"assistant","type":"act","action":"select_images","selected_images":[
  {"path":"xxx.png","reason":"..."},
  {"path":"https://example.com/chart.png","reason":"..."}
]}
```

**Blackboard 写入**
```json
{"regions":{"selected_images":{"images":[
  {"path":"xxx.png","reason":"..."},
  {"path":"https://example.com/chart.png","reason":"..."}
]}}}
```

**上下文**
```
[ACT select_images] xxx.png: 一句话说明为什么保留这张图
[ACT select_images] https://example.com/chart.png: 一句话说明为什么保留这张图
```

`selected_images` 区域随 `## Blackboard` 段以文本注入所有 LLM 阶段；模型支持图片且 `meta.use_images` 开启时，这些图片会排在上一次代码执行生成的 `images` 之后作为 `image_url` 内容提交。

---

## 5. generate_and_execute

**输入**
```json
{"action": "generate_and_execute", "research_guide": "..."}
```

**输出（成功）**
```json
{"role":"assistant","type":"act","action":"generate_and_execute","code":"...","result":"...","images":["xxx.png"]}
```

**输出（失败）**
```json
{"role":"assistant","type":"act","action":"generate_and_execute","error":"..."}
// code、result、images 在非空时可选出现
{"role":"assistant","type":"act","action":"generate_and_execute","error":"...","code":"...","result":"...","images":["xxx.png"]}
```

**上下文（成功）**
```
[ACT generate_and_execute] code:
{code}
[ACT generate_and_execute] result:
{result}
```

**上下文（失败）**
```
[ACT generate_and_execute] code:
{code}
[ACT generate_and_execute] error:
{error}
```

`images` 为本次执行生成的图片列表（去重后；本地图片通常只存文件名，本机静态地址或外部 http 图片保留完整 URL）。`act` 条目的该字段仅用于前端展示，不进入 LLM 上下文（`history_to_text` 不渲染该字段）；同时会覆盖写入 blackboard 的 `images` 区域，并随 `## Blackboard` 段以文本注入所有 LLM 阶段。若模型 `supports_images=true` 且请求 `meta.use_images` 开启，这些图片还会作为 `image_url` 内容数组附加到用户消息中，每张图片前带 `Image filename: ...` 标签。

---

## 6. output_text

**输入**
```json
{"action": "output_text", "text": "..."}
```

**输出**
```json
{"role":"assistant","type":"act","action":"output_text","text":"..."}
```

**上下文**
```
[ACT output_text] text:
{text}
```

---

## 7. ask_question

**输入**
```json
{"action": "ask_question", "text": "..."}
```

**输出**
```json
{"role":"assistant","type":"act","action":"ask_question","text":"..."}
```

**上下文**
```
[ACT ask_question] text:
{text}
```

---

## 8. ask_choice

**输入**
```json
{"action": "ask_choice", "text": "...", "choices": ["A", "B"]}
```

**输出**
```json
{"role":"assistant","type":"act","action":"ask_choice","text":"...","choices":["A","B"]}
```

**上下文**
```
[ACT ask_choice] text:
{text}
```

---

## 9. summary_and_pause

**输入**
```json
{"action": "summary_and_pause", "text": "..."}
```

**输出**
```json
{"role":"assistant","type":"act","action":"summary_and_pause","text":"..."}
```

**上下文**
```
[ACT summary_and_pause] text:
{text}
```

---

## 10. attempt_completion

**输入**
```json
{"action": "attempt_completion", "text": "..."}
```

**输出**
```json
{"role":"assistant","type":"act","action":"attempt_completion","text":"..."}
```

**上下文**
```
[ACT attempt_completion] text:
{text}
```

---

## 11. generate_document

**输入**
```json
{"action": "generate_document", "title": "..."}
```

**输出**
```json
{"role":"assistant","type":"act","action":"generate_document","title":"...","file_name":"...","full_text":"..."}
```

**上下文**
```
[ACT generate_document] file_name: {file_name}.md / .docx
[ACT generate_document] full_text:
{full_text}
```

---

## 12. web_search

**输入**
```json
{"action": "web_search", "query": "...", "max_results": 10}
```

**输出**
```json
{"role":"assistant","type":"act","action":"web_search","search_result":"...","query":"..."}
```

**上下文**
```
[ACT web_search] search_result:
{search_result}
[ACT web_search] query: {query}
```

---

## 13. fetch_webpage

**输入**
```json
{"action": "fetch_webpage", "url": "...", "max_length": 10000}
```

**输出**
```json
{"role":"assistant","type":"act","action":"fetch_webpage","url":"...","page_content":"..."}
```

**上下文**
```
[ACT fetch_webpage] page_content:
{page_content}
[ACT fetch_webpage] url: {url}
```

---

#---

## 14. explore_mcp

**输入**
```json
{"action": "explore_mcp", "keyword": "..."}
```
keyword 为可选提示词，传递给 LLM 作为关注重点的提示。连接所有配置的 MCP 服务器并获取全部工具列表，由 LLM 筛选。

**输出**
```json
{"role":"assistant","type":"act","action":"explore_mcp",
 "selected_tools":[{"server":"calculator","name":"calculate"},...],
 "explore_plan":"..."}
```

**Blackboard 写入**
```json
{"regions":{"mcp":{"selected_tools":[...],"explore_plan":"...","tool_detail":"...","catalog":"..."}}}
```

**上下文（成功）**
```
[ACT explore_mcp] selected_tools: [{"server":"calculator","name":"calculate"},...]
[ACT explore_mcp] explore_plan:
{plan}
```

完整 `tool_detail` / `catalog` 只保存在 blackboard。

---

## 15. exe_mcp

**输入**
```json
{"action": "exe_mcp", "server": "server_name", "tool": "tool_name", "params": {"key": "value"}}
```
单工具格式，由 `explore_mcp` 选出的 `selected_tools` 指定。params 为可选参数。

也支持多工具格式（批量执行）：
```json
{"action": "exe_mcp", "tools": [{"server": "...", "tool": "...", "params": {...}}, ...]}
```

**输出**
```json
{"role":"assistant","type":"act","action":"exe_mcp",
 "results":[{"server":"...","tool":"...","result":{...}},...],
 "error":null}
```

**上下文（成功）**
```
[ACT exe_mcp] {server}/{tool} result:
{result_json}
```

**上下文（失败）**
```
[ACT exe_mcp] {server}/{tool} error: {error}
```

---

## 16. Observe

**输入**
```json
{"question": "...", "session_id": "...", "conversation_history": [...], "cycle_index": 0}
```

**输出**
```json
{"role":"assistant","type":"observe","content":{"description":"...","todo":["..."]}}
```

**上下文**
```
[OBSERVE] content:
{"description": "...", "todo": ["...", "..."]}
```

---

## 17. 用户反馈

**选择**
```
输出: {"role":"user","type":"choice","content":"..."}
上下文: User chose: {content}
```

**回复**
```
输出: {"role":"user","type":"response","content":"..."}
上下文: User response: {content}
```

**输入**
```
输出: {"role":"user","type":"input","content":"..."}
上下文: User: {content}
```

**提问**
```
输出: {"role":"user","type":"question","content":"..."}
上下文: Q: {content}
```