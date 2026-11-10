# 如何新增 Action

以下步骤说明如何新增一个动作（Action）及其对应的执行逻辑（Act）。

## 步骤概览

| 步骤 | 文件 | 修改内容 |
|------|------|----------|
| 1 | `agent/action.py` | 注册动作名称、添加 LLM 提示词、解析参数 |
| 2 | `agent/act.py` | 添加执行函数、注册分发路由 |
| 3 | `agent/document_generator.py` 或新文件 | 实现具体执行逻辑 |
| 4 | `utils/context_trim.py` | 添加历史截断保留策略 |
| 5 | `utils/front_utils.py` | 添加历史文本格式化 |
| 6 | 前端 `useChat.js` | 处理前端逻辑（如需要） |
| 7 | 前端 `ActMessage.vue` | 添加子阶段显示标签（如需要） |
| 8 | `docs/sse_event_flow.md` | 更新 SSE 事件流文档 |
| 9 | `docs/conversation_history_structure.md` | 更新历史结构文档 |

## 详细步骤

### 1. `agent/action.py` — 注册动作

**a) 添加到 `VALID_ACTIONS` 列表**

```python
VALID_ACTIONS = [
    ...
    "my_new_action",
]
```

若新动作受功能开关控制，需像 `explore_base_knowledge` / `web_search` / `fetch_webpage` / `explore_mcp` / `exe_mcp` 一样在开关为真时条件追加：

```python
if ENABLE_WEB_SEARCH:
    VALID_ACTIONS.append("web_search")
```

并在 `agent/act.py` 的 `_DISABLED_ACTIONS` 中为关闭状态登记一条原因，开关关闭时由 `_event_stream_act_impl` 中已有的 `if action in _DISABLED_ACTIONS:` 守卫返回错误：

```python
_DISABLED_ACTIONS = {}
if not _ENABLE_WEB_SEARCH:
    _DISABLED_ACTIONS["web_search"] = "Web search support is disabled in config"
```

**b) 在 `_ACTION_DESCRIPTIONS` 中添加提示词**

每个 action 的提示文本都定义在 `agent/action.py` 的 `_ACTION_DESCRIPTIONS` 字典中，`ACTIONS` / `ACTIONS_BODY` 会按 `VALID_ACTIONS` 的顺序拼接生成。新增动作时直接新增一个字典条目，不要编辑 `ACTIONS` 字符串（它由 `_ACTION_DESCRIPTIONS` 生成，且新 action 不在字典中会触发 `KeyError`）：

```python
_ACTION_DESCRIPTIONS["my_new_action"] = """- my_new_action: {{"action": "my_new_action", "param1": "value1"}}
  描述该动作的作用和使用场景。"""
```

**c) 在 `_parse_action_json` 中提取参数**

```python
return {
    ...
    "param1": result.get("param1"),
}
```

**d) 若需支持多动作批量执行**

多动作由 `actions` 数组触发，`_parse_action_json` 逐项校验后交给 `_build_multi_action_result` 重建每个条目的字段。要支持批量还需：
- 把 action 名加入 `_GROUP_1_ACTIONS`（探索/选图类）或 `_GROUP_2_ACTIONS`（用户交互类）。解析器只强制 Group 1 与 Group 2 不能混用，其他动作的“只能单独执行”仅由提示词约束，不在解析器中强制。
- 在 `_build_multi_action_result` 中为每个条目补充需要保留的字段（该函数按白名单字段逐项重建）。

### 2. `agent/act.py` — 添加执行逻辑

**a) 导入执行函数**

```python
from agent.some_module import some_exec_function
```

**b) 在 `_event_stream_act_impl` 中添加路由**

路由分发逻辑位于 `_event_stream_act_impl`；`_event_stream_act` 只是包一层的 try/except 守卫，把未捕获异常转成终止性 error 事件，不承载各 action 的 `if/elif` 分发。

```python
elif action == "my_new_action":
    param1 = params.get("param1")
    act_data = yield from _act_my_new_action(..., param1, ...)
```

**c) 实现执行函数**

```python
def _act_my_new_action(full_question, session_id, param1, request_json=""):
    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'my_new_action', 'type': 'msg', 'content': '正在执行...'}, ensure_ascii=False)}\n\n"

    # 执行具体逻辑，yield SSE 事件
    for event in some_exec_function(...):
        yield f"data: {json.dumps({**event}, ensure_ascii=False)}\n\n"

    return {"param1": param1, "status": "completed"}
```

**d) 在 `_build_act_entries` 中添加历史记录**

```python
elif action == "my_new_action":
    param1 = act_data.get("param1", "")
    entries.append({"role": "assistant", "type": "act", "action": "my_new_action", "param1": param1, "result": "执行完成"})
```

### 3. 实现具体执行逻辑

可以是新文件或现有文件中的函数。函数应为生成器（generator），SSE 事件格式统一为 `{phase, sub_phase, type, content, ...}`。现有代码有两种流式输出模式：

- **预序列化 SSE 字符串（主流做法）**：绝大多数 `_act_*` 执行函数直接 yield 已序列化的 SSE 文本行（参照 `_act_explore_schema` / `_act_web_search` 等）：

```python
yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'my_new_action', 'type': 'msg', 'content': '...'}, ensure_ascii=False)}\n\n"
yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'my_new_action', 'type': 'chunk', 'content': '...'}, ensure_ascii=False)}\n\n"
yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'my_new_action', 'type': 'done', 'content': '...', 'key': 'value'}, ensure_ascii=False)}\n\n"
```

- **事件字典流（仅 generate_and_execute 使用）**：底层 `generate_and_execute_stream`（`agent/agent.py`）yield 事件字典，由 `_act_generate_and_execute` 消费后再包装成上述 `data: ...\n\n` 字符串转发。新增 action 建议直接采用第一种模式，不要新增 dict 流。

### 4. `utils/context_trim.py` — 历史截断策略

**a) 添加到 `HISTORY_RETENTION`**

```python
HISTORY_RETENTION = {
    ...
    "act_my_new_action": 999,  # 永久保留，或根据需求设置
}
```

**b) 在 `_get_entry_category` 中添加分类**

```python
if action == "my_new_action":
    return "act_my_new_action"
```

### 5. `utils/front_utils.py` — 历史文本格式化

在 `history_to_text` 中添加格式化逻辑：

```python
elif action == "my_new_action":
    if entry.get("param1"):
        lines.append(f"[ACT my_new_action] 参数: {entry['param1']}")
    if entry.get("result"):
        lines.append(f"[ACT my_new_action] Result:\n{entry['result']}")
```

> 如果新 action 属于探索类并会产生大段搜索结果，不要写入 act 条目，应按照 `explore_schema` / `explore_functions` / `explore_base_knowledge` / `explore_mcp` 的方式写入 blackboard，并在 `blackboard_section` 中渲染。否则搜索结果会进入上下文并造成重复。

### 6. 前端 `useChat.js` — 参数传递

在 `runActPhase` 的 `params` 对象中传递新参数：

```javascript
params: {
    ...
    param1: actionResult.param1 || undefined,
}
```

### 7. 前端 `ActMessage.vue` — 子阶段标签

在 `subPhaseLabel` 中添加显示名称：

```javascript
function subPhaseLabel(name) {
    const labels = {
        ...
        my_new_action: 'My New Action',
    }
    return labels[name] || name
}
```

### 8. `docs/sse_event_flow.md` — 文档

在 act 章节下添加 SSE 事件流说明：

```markdown
### my_new_action

```
成功：
  {type:"msg",     sub_phase:"my_new_action", content:"正在执行..."}
  {type:"chunk",   sub_phase:"my_new_action", content:"..."}  ×N
  {type:"done",    sub_phase:"my_new_action", content:"...", param1:"..."}
  {type:"history", history:[...]}
```
```

### 9. `docs/conversation_history_structure.md` — 文档

在 act 章节下添加历史结构说明：

```markdown
### my_new_action

```json
{"role":"assistant","type":"act","action":"my_new_action",
 "param1":"...","result":"执行完成"}
```
```

## 完整示例：`web_search` 动作

### 作用
搜索网络信息，使用 DuckDuckGo 引擎，返回标题、URL、摘要。

### 实现要点
- **`action.py`**: `VALID_ACTIONS` 添加 `"web_search"`，`_ACTION_DESCRIPTIONS` 添加 `query`/`max_results` 参数描述，`_parse_action_json` 提取 `query`/`max_results`
- **`act.py`**: 导入 `search_web`，`_event_stream_act_impl` 分发到 `_act_web_search`，`_build_act_entries` 保存 `search_result` 和 `query`
- **执行函数**: 直接调用 `search_web(query, max_results)`，结果格式化为 markdown 后 yield `done` 事件
- **前端**: `useChat.js` params 传递 `query`/`max_results`，`ActMessage.vue` 添加 `web_search` 模板和 `subPhaseLabel`

### SSE 事件流
```
成功：
  {type:"msg",     sub_phase:"web_search", content:"Searching: {query}..."}
  {type:"chunk",   sub_phase:"web_search", content:"搜索结果 markdown..."}
  {type:"done",    sub_phase:"web_search", content:"...", result:{search_results:{...}, query:"..."}}
  {type:"history", history:[...]}

失败：
  {type:"error",   sub_phase:"web_search", content:"Search failed: ..."}
```

## 完整示例：`fetch_webpage` 动作

### 作用
获取指定 URL 的网页文本内容，通常用于 `web_search` 之后阅读详细页面。

### 实现要点
- **`action.py`**: `VALID_ACTIONS` 添加 `"fetch_webpage"`，`_ACTION_DESCRIPTIONS` 添加 `url`/`max_length` 参数描述，`_parse_action_json` 提取 `url`/`max_length`
- **`act.py`**: 导入 `fetch_webpages`（复数，来自 `agent/tools/web_search/web_search.py`），`_event_stream_act_impl` 分发到 `_act_fetch_webpage`，`_build_act_entries` 保存 `url` 和 `content`（存入 `page_content` 字段）
- **执行函数**: act 流程调用的是 `fetch_webpages(urls, max_length)`（URL 列表，最多 10 个，并行抓取）；单页版 `fetch_webpage(url, max_length)` 是同一文件中的另一个独立工具函数，act 流程不使用。返回内容 yield `chunk` 和 `done` 事件
- **前端**: `useChat.js` params 传递 `url`/`max_length`，`ActMessage.vue` 添加 `fetch_webpage` 模板和 `subPhaseLabel`

### SSE 事件流
```
成功：
  {type:"msg",     sub_phase:"fetch_webpage", content:"Fetching {N} page(s) in parallel..."}
  {type:"chunk",   sub_phase:"fetch_webpage", content:"## Page Content ({N} page(s))..."}
  {type:"done",    sub_phase:"fetch_webpage", content:"...", result:{urls:[...], url:"...", pages:[...], content:"..."}}
  {type:"history", history:[...]}

说明：抓取流程本身不单独发送 error 事件；单个页面失败时该页在 `pages` 中带 `error`，
      并在合并内容中显示 "> Failed: ..."，其余页面照常返回。
```

## 完整示例：`generate_document` 动作

参考已实现的 `generate_document` 动作，该动作：
- 在 `action.py` 中注册为 `VALID_ACTIONS`，并在 `_ACTION_DESCRIPTIONS` 添加提示
- 在 `act.py` 中通过 `_act_generate_document` 执行
- 调用 `document_generator.py` 中的 `generate_document_from_context`
- SSE 事件使用 `phase: 'act'` + `sub_phase: 'generate_document'`
- 历史记录通过 `_build_act_entries` 保存为 `{"role":"assistant","type":"act","action":"generate_document","title":"...","file_name":"...","full_text":"...","download_url_md":"...","download_url_docx":"...","download_url_pdf":"..."}`（没有 `result` 字段）