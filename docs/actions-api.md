# Actions API 文档

Action 分为两类：**后端 action**（调用 `POST /api/act/stream/`）和**前端 action**（纯前端执行，无 API 调用）。

所有 action 的文本内容均由 **Action 阶段 LLM** 一次性生成，Act 阶段不再调用 LLM。

---

## 后端 Action（需调用 API）

端点：`POST /api/act/stream/`  
响应：`Content-Type: text/event-stream`

### 通用上下文（所有请求体均包含）

```json
{
  "question": "string - 对话历史上下文",
  "action": "string - 动作名称",
  "session_id": "string",
  "tables": ["table1"],
  "conversation_history": ["Q: ...", "Planner: ...", "Selected Fields: ..."],
  "selected_fields": {"table1": ["col1"]},
  "selected_functions": ["exe_sql"],
  "params": {}
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `question` | string | 对话历史上下文（`"\n".join(conversation_history)`） |
| `action` | string | 动作名称 |
| `session_id` | string | 会话 ID |
| `tables` | [string] | 可选，限制搜索的表名列表 |
| `conversation_history` | [string] | 对话历史 |
| `selected_fields` | object | 可选，当前已选中的表字段（来自之前的 search_db） |
| `selected_functions` | [string] | 可选，当前已选中的函数（来自之前的 search_func） |
| `params` | object | 动作特定参数，结构取决于 action |

---

### 1. search_db

搜索数据库表结构，LLM 筛选所需字段。

#### 请求体

在通用上下文基础上，`params` 为：

```json
{
  "action": "search_db",
  "params": {
    "search_keyword": "keyword1 keyword2"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `search_keyword` | string | 否 | 关键词，空格分隔多关键词。为空则返回全部表 |

#### 响应 SSE 事件

```
data: {"phase":"act","sub_phase":"search_db","type":"status","content":"正在搜索数据库信息..."}
data: {"phase":"act","sub_phase":"search_db","type":"status","content":"正在分析所需字段..."}
data: {"phase":"act","sub_phase":"search_db","type":"done","content":"表结构 markdown...","result":{...}}
```

#### done 事件 result

```json
{
  "selected_fields": {
    "table1": ["col1", "col2"],
    "table2": []
  },
  "db_context": "原始搜索结果 markdown"
}
```

`selected_fields` 取值：
- `{"table": ["col1"]}` → 指定表和列
- `{"table": []}` → 该表所有列
- `{}` → 所有表所有列
- `{"__no_db__": true}` → 无需数据库

---

### 2. search_func

搜索可用函数，LLM 筛选所需函数。

#### 请求体

在通用上下文基础上，`params` 为：

```json
{
  "action": "search_func",
  "params": {
    "search_keyword": "keyword"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `search_keyword` | string | 否 | 关键词。为空则返回全部函数 |

#### 响应 SSE 事件

```
data: {"phase":"act","sub_phase":"search_func","type":"status","content":"正在搜索函数信息..."}
data: {"phase":"act","sub_phase":"search_func","type":"status","content":"正在分析所需函数..."}
data: {"phase":"act","sub_phase":"search_func","type":"done","content":"函数文档 markdown...","result":{...}}
```

#### done 事件 result

```json
{
  "selected_functions": ["exe_sql", "load_data"],
  "func_context": "原始函数目录 markdown"
}
```

---

### 3. generate_and_execute

生成代码并执行。

#### 请求体

在通用上下文基础上，`selected_fields` 和 `selected_functions` 由之前的 search 阶段填充，`params` 为空：

```json
{
  "action": "generate_and_execute",
  "selected_fields": {"table1": ["col1", "col2"]},
  "selected_functions": ["exe_sql"],
  "params": {}
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `selected_fields` | object | 否 | search_db 选中的表字段 |
| `selected_functions` | [string] | 否 | search_func 选中的函数名 |

#### 响应 SSE 事件

```
data: {"phase":"act","sub_phase":"generate","type":"status","content":"正在生成并执行代码..."}
data: {"phase":"act","sub_phase":"code","type":"status","content":"正在分析问题..."}
data: {"phase":"act","sub_phase":"code","type":"status","content":"正在生成代码..."}
data: {"phase":"act","sub_phase":"code","type":"code_chunk","content":"def "}
data: {"phase":"act","sub_phase":"code","type":"code_chunk","content":"main():"}
data: {"phase":"act","sub_phase":"code","type":"code_complete","content":"def main():\n    ..."}
data: {"phase":"act","sub_phase":"exec","type":"status","content":"正在执行代码..."}
data: {"phase":"act","sub_phase":"exec","type":"chunk","content":"output line 1\n"}
data: {"phase":"act","sub_phase":"exec","type":"done","content":"","result":{...}}
```

异常路径：`code` → `solved`（无需代码）、`exec` → `error`（执行失败）

#### done 事件 result

```json
{
  "code": "def main():\n    import pandas as pd\n    ...",
  "exec_result": "执行输出文本",
  "error": null
}
```

---

## 前端 Action（无需 API，纯前端执行）

以下 5 个 action 的内容由 Action 阶段 LLM 一次性生成，前端直接显示，不调用后端 API。

### 4. output_text

显示文本回复。

**Action 阶段输出：**
```json
{"action": "output_text", "text": "完整回复文本（markdown）"}
```

**前端行为：** 直接渲染 `text` 为 markdown，继续下一循环。

---

### 5. ask_question

向用户提问。

**Action 阶段输出：**
```json
{"action": "ask_question", "text": "请问您想查询哪个表的数据？"}
```

**前端行为：** 显示问题文本，弹出输入框等待用户输入。输入写入 `conversation_history` 为 `"User response: {text}"`，继续下一循环。

---

### 6. ask_choice

向用户提供选项。

**Action 阶段输出：**
```json
{
  "action": "ask_choice",
  "text": "请选择要查询的数据集",
  "choices": ["brset", "odir", "m3ret"]
}
```

**前端行为：** 显示问题和选项，等待用户选择。选择写入 `conversation_history` 为 `"User chose: {text}"`，继续下一循环。

---

### 7. summary_and_pause

总结进度并暂停。

**Action 阶段输出：**
```json
{"action": "summary_and_pause", "text": "已完成数据查询，共找到 100 条记录..."}
```

**前端行为：** 显示总结文本，弹出输入框等待用户指令。输入写入 `conversation_history` 为 `"User: {text}"`，继续下一循环。

---

### 8. attempt_completion

任务完成。

**Action 阶段输出：**
```json
{"action": "attempt_completion", "text": "分析完成。主要发现：1. ..."}
```

**前端行为：** 显示最终结果文本，弹出"下一步?"输入框等待新问题。新问题重置 `conversation_history` 为 `["Q: {new_question}"]`。

---

## 总览

| # | Action | 执行方式 | 调用 LLM | 用户交互 |
|---|--------|---------|---------|---------|
| 1 | `search_db` | 后端 API | 是（筛选字段） | 否 |
| 2 | `search_func` | 后端 API | 是（筛选函数） | 否 |
| 3 | `generate_and_execute` | 后端 API | 是（生成代码） | 否 |
| 4 | `output_text` | 前端 | 否 | 否 |
| 5 | `ask_question` | 前端 | 否 | 是（输入文本） |
| 6 | `ask_choice` | 前端 | 否 | 是（单选） |
| 7 | `summary_and_pause` | 前端 | 否 | 是（输入文本） |
| 8 | `attempt_completion` | 前端 | 否 | 是（新问题） |