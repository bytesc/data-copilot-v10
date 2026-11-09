# Action 输入输出文档

> 文中 API 入参示例展示的是统一请求信封中的 `data` 内容；实际发送到后端的 JSON `POST/PUT/PATCH`
> 请求体必须为 `{"meta": {"model": "...", "reasoning_effort": "...", "style": "...", "use_images": true}, "data": {...}}`。

每个环节记录三项：**输入**（LLM 决策输出的 JSON / API 入参）、**输出**（写入 `conversation_history` 的条目）、**上下文**（`history_to_text` 转换后喂给 LLM 的文本）。

> 除下文列出的上下文外，每个 LLM 阶段还会额外注入独立的 `## Blackboard` 段（`blackboard_section(conversation_history)`），用于提供完整的 DB schema、函数文档、业务知识和 MCP 工具详情。blackboard 不进入 `history_to_text`，详见 `docs/conversation_history_structure.md`。blackboard 的 `recent_generated_images` 区域（最近一次代码执行生成的图片列表）和 `selected_images` 区域（`select_images` 选中或用户上传的图片及原因）也随该段以文本注入；当模型 `supports_images=true` 且请求 `meta.use_images` 开启时，两处图片会按 `recent_generated_images` 在前、`selected_images` 在后的顺序以 `image_url` 内容数组的形式随请求提交（本地文件/本机静态 URL 转 base64，外部 URL 原样传递，详见 `docs/conversation_history_structure.md`）。

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
{"role":"assistant","type":"action_decision","content":{"actions":[{"action":"ask_question","text":"..."},{"action":"ask_choice","text":"...","choices":["..."]}]}}
```

Group 1（`explore_*` / `select_images`）和 Group 2（`ask_question` / `ask_choice` / `summary_and_pause` / `attempt_completion`）不能混在同一个 `actions` 数组中。例如 `[{"action":"select_images",...},{"action":"ask_question",...}]` 是非法的，后端会拒绝并要求重新决策；需要选图并说明时应拆成两个 cycle。解析器只强制上述 Group 1 / Group 2 互斥；其余 action（`generate_and_execute` / `generate_document` / `web_search` / `fetch_webpage` / `exe_mcp`）的“只能单独执行”仅由提示词约束（见 `agent/action.py` 的 `ACTIONS` 文本），`_parse_action_json` 并不会拒绝把它们放进 `actions` 数组。

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
| `keyword` | 任意单动作均可解析；仅 explore_schema / explore_functions / explore_base_knowledge / explore_mcp 会消费 | 可选 | 其他 action 携带时被忽略；explore_* 中为空则不附加关注提示，不用于过滤数据。act 层参数名：决策层字段为 `keyword`，前端会把 `actionResult.keyword` 映射为 `params.search_keyword` 再调用 `/api/act/stream/`；act 层同时接受 `search_keyword` 与 `keyword` 两个名字（`agent/act.py`） |
| ~~`funcs`~~ | generate_and_execute | 已移除 | 函数名统一从 blackboard 的 `functions.selected_functions` 读取 |
| `research_guide` | generate_and_execute | 可选 | 为空，不提供额外研究提示 |
| `text` | ask_question / ask_choice / summary_and_pause / attempt_completion | 前端交互必填 | 缺少时前端无可展示/提问的内容 |
| `choices` | ask_choice | ask_choice 必填（至少一项） | 其他 action 中无效 |
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
| `images` | select_images | 必填（可为空数组） | 为空数组时清空 `selected_images` 区域；每项为 `{"path", "reason"}` |

SSE `done` 事件的 `action_result` 只保留上述字段（由 `agent/action.py` 的 `_parse_action_json` 规范化），未列出的字段会被丢弃；但写入 `conversation_history` 的 `action_decision` 条目保存的是 LLM 的完整原始 JSON（`agent/action.py` 通过 `parse_json_raw(raw)` 保存），不做字段裁剪。

**功能开关**

以下 action 只有在配置开启对应开关时才有效；未开启时 `agent/action.py` 不会把它们追加进 `VALID_ACTIONS`（决策会被判定为未知 action），`agent/act.py` 也会通过 `_DISABLED_ACTIONS` 直接返回错误。开关关闭时还会省略其提示词、分组与相关决策规则。

| action | 开关（`config_data`） |
| --- | --- |
| explore_base_knowledge | `enable_base_knowledge` |
| web_search | `enable_web_search` |
| fetch_webpage | `enable_fetch_url` |
| explore_mcp / exe_mcp | `enable_mcp` |

> 这些开关只作用于 **action 层**：关闭后该 action 会从 `VALID_ACTIONS` 移除，`act.py` 也会通过 `_DISABLED_ACTIONS` 直接拒绝。开关**不改变代码生成阶段可用的函数目录**：例如 `exe_mcp` 虽受 `enable_mcp` 门控，但 `agent/tools/get_function_info.py` 的 `FUNCTION_DICT` 中始终包含 `exe_mcp` 函数，因此它仍会出现在函数选择列表里、生成的代码也仍可调用它。

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
[ACT explore_functions] error:
{error}
```

解析失败时 act 条目会写入 `"error": "explore_functions parse failed; previous selection preserved"`，渲染为上面的 error 行；此时不覆盖 blackboard，沿用上一次的函数选择。

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

`path` 为本地 `tmp_imgs` 下的图片文件名，或完整的 `http(s)` 图片链接；`reason` 为每个图片的一句话选中原因。可选图片包括当前 `recent_generated_images` 区域中的图片、**本会话更早轮次生成过的图片**、会话附件图片和上下文中出现的图片 URL；`recent_generated_images` 只保留最近一次代码执行的图片，因此更早生成的图片即使不在该区域中，也仍然可以被选中，不应据此判断图片已丢失。历史 `generate_and_execute` 结果中的 markdown 图片 URL（如 `.../tmp_imgs/xxx.png`）可用于提取文件名；用户按“第二张”等位置或描述指代旧图时，应从历史中解析对应文件名并直接选中，而不是要求用户重新生成。该 action 属于 Group 1，可与 `explore_*` 动作在同一次 `actions` 数组中批量执行，但不能与 `ask_question` / `ask_choice` / `summary_and_pause` / `attempt_completion` 混用。当前 `selected_images` 已经包含相同路径时不要重复调用；只有选中集合实际变化时才更新。重复执行会**整体覆盖** `selected_images` 区域；`images: []` 会清空该区域。当用户需求变化（新范围、新分析目标或纠正）时，应重新运行 `select_images` 更新该区域，而不是保留过期的选中图片。

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

`selected_images` 区域随 `## Blackboard` 段以文本注入所有 LLM 阶段；模型支持图片且 `meta.use_images` 开启时，这些图片会排在上一次代码执行生成的 `recent_generated_images` 之后作为 `image_url` 内容提交。

---

## 5. generate_and_execute

**输入**
```json
{"action": "generate_and_execute", "research_guide": "..."}
```

如果用户只是要求查看、观察或描述已有图片，不应调用本 action 重新生成；应先通过 `select_images` 选中原始图片文件名。

**输出（成功）**
```json
{"role":"assistant","type":"act","action":"generate_and_execute","exec_ok":true,"code":"...","result":"...","images":["xxx.png"]}
```

成功条目始终携带 `"exec_ok": true`，且 `result` 字段始终存在（可能为空字符串）；`code` 与 `images` 仅在非空时写入。`exec_ok` 由历史截断分类（`utils/context_trim.py`）和前端渲染（`utils/front_utils.py`）用来把"执行成功但无文本输出"的条目识别为真实执行结果。

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

执行成功但没有文本输出时，`result` 为空，上下文渲染为 `[ACT generate_and_execute] result: (executed successfully; no textual output)`（依据条目的 `exec_ok` 标记）。

**上下文（失败）**
```
[ACT generate_and_execute] code:
{code}
[ACT generate_and_execute] error:
{error}
```

`images` 为本次执行生成的图片列表（去重后；本地图片通常只存文件名，本机静态地址或外部 http 图片保留完整 URL）。`act` 条目的该字段仅用于前端展示，不进入 LLM 上下文（`history_to_text` 不渲染该字段）；同时会覆盖写入 blackboard 的 `recent_generated_images` 区域，并随 `## Blackboard` 段以文本注入所有 LLM 阶段。若模型 `supports_images=true` 且请求 `meta.use_images` 开启，这些图片还会作为 `image_url` 内容数组附加到用户消息中，每张图片前带 `Image filename: ...` 标签。

---

## 6. ask_question

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

## 7. ask_choice

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

## 8. summary_and_pause

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

## 9. attempt_completion

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

## 10. generate_document

**输入**
```json
{"action": "generate_document", "title": "..."}
```

**输出**
```json
{"role":"assistant","type":"act","action":"generate_document","title":"...","file_name":"...","full_text":"...",
 "download_url_md":"...","download_url_docx":"...","download_url_pdf":"..."}
```

文档始终生成 `.md`；`.docx` 与 `.pdf` 在转换成功时生成。失败时两个字段的表现取决于读取位置：SSE `done` 事件把转换失败的 `download_url_docx` / `download_url_pdf` 置为空字符串（`agent/document_generator.py`，`download_url_md` 始终非空）；而写入 `conversation_history` 的 act 条目则由 `agent/act.py` 仅按 `file_name` 重新拼出全部三个 URL，只要 `file_name` 存在即非空——即使转换失败，对应的 `.docx` / `.pdf` URL 也可能是指向不存在文件的死链。

**上下文**
```
[ACT generate_document] file_name: {file_name}.md / {file_name}.docx
[ACT generate_document] full_text:
{full_text}
```

`download_url_md` / `download_url_docx` / `download_url_pdf` 只写入历史条目用于前端下载，`history_to_text` 不渲染它们。

---

## 11. web_search

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

## 12. fetch_webpage

**输入**
```json
{"action": "fetch_webpage", "urls": ["https://a.com/1", "https://b.com/2"], "max_length": 10000}
```

`urls` 为 URL 数组（1-10 个），并行抓取后合并为一段 markdown 正文返回到 `content`/`page_content`；单页失败会在合并内容中显示 `> Failed: ...`，不影响其他页面。仅传单个 `url` 字符串时也可用。

**输出**（每个 URL 生成一条 act 条目，按输入顺序）
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

## 13. explore_mcp

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

## 14. exe_mcp

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
 "display_content":"..."}
```

`results`、`display_content`、`error` 三个字段仅在非空时写入条目：成功时没有 `error` 键（不是 `error:null`），只有存在错误时才会出现 `"error":"..."`。`display_content` 是所有工具执行结果的合并展示文本（以 `## MCP Tool Execution Results` 开头）。

**上下文（成功）**
```
[ACT exe_mcp] {server}/{tool} result:
{result_json}
[ACT exe_mcp] result:
{display_content}
```

**上下文（失败）**

单个工具失败：
```
[ACT exe_mcp] {server}/{tool} error: {error}
```

整次执行失败（如未提供可用工具）：
```
[ACT exe_mcp] error: {error}
```

---

## 15. Observe

**输入**
```json
{"question": "...", "session_id": "...", "conversation_history": [...], "cycle_index": 0}
```

**输出**
```json
{"role":"assistant","type":"observe","content":{"description":"...","todo":["..."]},"action":"generate_and_execute"}
```

条目可携带可选的顶层 `action` 键（`agent/observe.py` 取最近一条 act 条目的 action），用于历史截断按 `observe_<action>` 分类保留（`utils/context_trim.py`）；本轮没有前置 act 条目时省略该键。

**上下文**
```
[OBSERVE] content:
{"description": "...", "todo": ["...", "..."]}
```

---

## 16. 用户反馈

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

**上传图片**

提问时可附带图片，写入 user 条目的 `uploaded` 字段（图片随本轮第一个 JSON 请求以 base64 提交，无独立上传接口）：
```
前端发送: {"role":"user","type":"question","content":"...","uploaded":[{"name":"a.png","data":"data:image/png;base64,..."}]}
后端摄取后: {"role":"user","type":"question","content":"...","uploaded":["upload_abcd1234.png"]}
上下文: Q: {content}
        Uploaded images: upload_abcd1234.png
```
后端在请求信封中间件（`utils/image_ingest.py`）把 base64 保存为 `tmp_imgs/upload_<8位小写字母>.png`，改写 `uploaded` 为文件名列表，并追加合并进 blackboard 的 `selected_images` 区域。详见 `docs/api.md` 的「用户上传图片」。