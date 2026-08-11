# Phases API 文档

四步循环：**Think → Action → Act → Observe**，每轮全部执行。

---

## 1. Think — 规划

端点：`POST /api/think/stream/`  
响应：`Content-Type: text/event-stream`

分析问题和可用资源，生成结构化计划。

### 请求体

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `question` | string | 是 | 用户问题 |
| `tables` | [string] | 否 | 可用的表名列表 |
| `session_id` | string | 否 | 会话 ID |
| `conversation_history` | [string] | 否 | 对话历史（包含所有上下文） |

### 响应 SSE 事件

```
data: {"phase":"think","sub_phase":"plan","type":"status","content":"正在生成分析计划..."}
data: {"phase":"think","sub_phase":"plan","type":"chunk","content":"{\"description\":\"..."}
data: {"phase":"think","sub_phase":"plan","type":"done","content":"原始 JSON","plan_result":{...}}
```

### done 事件 plan_result

```json
{
  "description": "分析策略描述（markdown）",
  "todo": ["搜索糖尿病相关表", "查询患者统计数据", "生成可视化"]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `description` | string | 整体分析策略描述 |
| `todo` | [string] | 可选，待办任务列表。空数组表示计划完成 |

---

## 2. Action — 决策

端点：`POST /api/action/stream/`  
响应：`Content-Type: text/event-stream`

根据当前上下文（计划、状态、数据库上下文），决定下一步执行哪个动作。

### 请求体

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `question` | string | 是 | 原始问题 |
| `tables` | [string] | 否 | 可用的表名列表 |
| `session_id` | string | 否 | 会话 ID |
| `conversation_history` | [string] | 否 | 对话历史（包含 selected_fields、selected_functions 等状态） |
| `current_plan` | string | 是 | Think/Observe 输出的 JSON 字符串 |
| `db_context` | string | 否 | search_db 返回的原始数据库上下文 |
| `func_context` | string | 否 | search_func 返回的原始函数目录 |
| `cycle_index` | int | 否 | 当前循环序号 |

### 响应 SSE 事件

```
data: {"phase":"action","type":"status","content":"正在决策下一步动作..."}
data: {"phase":"action","type":"chunk","content":"{\"action\":\"search_db\""}
data: {"phase":"action","type":"done","content":"原始 JSON","action_result":{...}}
```

### done 事件 action_result

**后端 action：**

| action | 请求 JSON |
|--------|----------|
| `search_db` | `{"action":"search_db","keyword":"可选关键词 空格分隔"}` |
| `search_func` | `{"action":"search_func","keyword":"可选关键词"}` |
| `generate_and_execute` | `{"action":"generate_and_execute","funcs":["exe_sql","load_data"]}` |

**前端 action：**

| action | 请求 JSON |
|--------|----------|
| `output_text` | `{"action":"output_text","text":"回复内容..."}` |
| `ask_question` | `{"action":"ask_question","text":"问题文本..."}` |
| `ask_choice` | `{"action":"ask_choice","text":"问题文本...","choices":["选项1","选项2"]}` |
| `summary_and_pause` | `{"action":"summary_and_pause","text":"总结内容..."}` |
| `attempt_completion` | `{"action":"attempt_completion","text":"最终结果..."}` |

### action_result 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `action` | string | 动作名称 |
| `keyword` | string | 仅 search_db/search_func，搜索关键词 |
| `funcs` | [string] | 仅 generate_and_execute，选中的函数名 |
| `text` | string | 仅前端 action，文本内容 |
| `choices` | [string] | 仅 ask_choice，选项列表 |

---

## 3. Observe — 审查

端点：`POST /api/observe/stream/`  
响应：`Content-Type: text/event-stream`

审查 Act 执行结果，更新计划（移除已完成任务，保留/修正未完成任务）。

### 请求体

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `question` | string | 是 | 原始问题 |
| `tables` | [string] | 否 | 可用的表名列表 |
| `session_id` | string | 否 | 会话 ID |
| `current_plan` | string | 是 | Think/Observe 输出的 JSON 字符串 |
| `conversation_history` | [string] | 否 | 对话历史（包含执行结果、错误等所有上下文） |
| `cycle_index` | int | 否 | 当前循环序号 |
| `db_context` | string | 否 | search_db 返回的原始数据库上下文 |
| `func_context` | string | 否 | search_func 返回的原始函数目录 |

### 响应 SSE 事件

```
data: {"phase":"observe","sub_phase":"review","type":"status","content":"正在审查执行结果..."}
data: {"phase":"observe","sub_phase":"review","type":"chunk","content":"{\"description\":\"..."}
data: {"phase":"observe","sub_phase":"review","type":"done","content":"原始 JSON","plan_result":{...}}
```

### done 事件 plan_result

```json
{
  "description": "执行结果审查（markdown）",
  "todo": ["剩余任务 1", "剩余任务 2"]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `description` | string | 执行结果审查说明 |
| `todo` | [string] | 仅包含待完成的任务。空数组 = 计划完成 |

---

## 循环流程

```
┌──────────────────────────────────────────────────┐
│                   Think (规划)                      │
│  输入: question, conversation_history              │
│  输出: {description, todo} → 写入 conversation_history │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────┐
│                  Action (决策)                      │
│  输入: question, conversation_history,             │
│        current_plan, db_context, func_context      │
│  输出: {action, keyword?, funcs?, text?, choices?} │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────┐
│                    Act (执行)                       │
│  后端: search_db / search_func / generate_and_execute│
│  前端: output_text / ask_question / ask_choice /   │
│        summary_and_pause / attempt_completion       │
│  结果写入 conversation_history:                     │
│    "Selected Fields: {json}"                       │
│    "Selected Functions: {json}"                    │
│    "Exe Result: {text}" / "Exe Error: {text}"      │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────┐
│                 Observe (审查)                      │
│  输入: question, conversation_history,             │
│        current_plan, db_context, func_context      │
│  输出: {description, todo} → 写入 conversation_history │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼ 下一轮 Think
```

### 状态传递

所有状态通过 `conversation_history` 传递，无需特殊管理：

| 状态 | 写入方式 | 内容 |
|------|---------|------|
| `current_plan` | `conversation_history` | `"Planner: {json}"` |
| `selected_fields` | `conversation_history` | `"Selected Fields: {json}"` |
| `selected_functions` | `conversation_history` | `"Selected Functions: {json}"` |
| `execution_result` | `conversation_history` | `"Exe Result: {text}"` |
| `execution_error` | `conversation_history` | `"Exe Error: {text}"` |
| `db_context` | 内部变量 | 传递给 Action/Observe 提示上下文 |
| `func_context` | 内部变量 | 传递给 Action/Observe 提示上下文 |