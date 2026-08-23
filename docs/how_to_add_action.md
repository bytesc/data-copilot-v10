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

**b) 添加到 `ACTIONS` 提示字符串**

```python
ACTIONS = """
...
- my_new_action: {{"action": "my_new_action", "param1": "value1"}}
  描述该动作的作用和使用场景。
"""
```

**c) 在 `_parse_action_json` 中提取参数**

```python
return {
    ...
    "param1": result.get("param1"),
}
```

### 2. `agent/act.py` — 添加执行逻辑

**a) 导入执行函数**

```python
from agent.some_module import some_exec_function
```

**b) 在 `_event_stream_act` 中添加路由**

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

可以是新文件或现有文件中的函数。函数应为生成器（generator），yield SSE 事件字典。

SSE 事件格式统一为：

```python
yield {"phase": "act", "sub_phase": "my_new_action", "type": "msg", "content": "..."}
yield {"phase": "act", "sub_phase": "my_new_action", "type": "chunk", "content": "..."}
yield {"phase": "act", "sub_phase": "my_new_action", "type": "done", "content": "...", "key": "value"}
```

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

### 10. `docs/conversation_history_structure.md` — 文档

在 act 章节下添加历史结构说明：

```markdown
### my_new_action

```json
{"role":"assistant","type":"act","action":"my_new_action",
 "param1":"...","result":"执行完成"}
```
```

## 完整示例：`generate_document` 动作

参考已实现的 `generate_document` 动作，该动作：
- 在 `action.py` 中注册为 `VALID_ACTIONS` 和 `ACTIONS` 提示
- 在 `act.py` 中通过 `_act_generate_document` 执行
- 调用 `document_generator.py` 中的 `generate_document_from_context`
- SSE 事件使用 `phase: 'act'` + `sub_phase: 'generate_document'`
- 历史记录通过 `_build_act_entries` 保存为 `{"role":"assistant","type":"act","action":"generate_document","title":"...","file_name":"...","result":"..."}`