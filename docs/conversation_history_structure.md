# conversation_history 结构定义

## think

LLM 输出的 JSON 对象，格式为 `{"description": "...", "todo": [...]}`。

```json
{"role":"assistant","type":"think","content":{"description":"...","todo":["..."]}}
```

## action

LLM 输出的 JSON 对象，格式为 `{"action": "...", ...}`。

```json
{"role":"assistant","type":"action_decision","content":{"action":"explore_schema","keyword":"..."}}
```

## act

### explore_schema

```json
{"role":"assistant","type":"act","action":"explore_schema",
 "selected_fields":{"table1":["col1","col2"],"table2":[]},"explore_plan":"...","search_result":"..."}
```

### explore_functions

```json
{"role":"assistant","type":"act","action":"explore_functions",
 "selected_functions":[...],"search_result":"..."}
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

### generate_document

```json
{"role":"assistant","type":"act","action":"generate_document",
 "file_name":"...","result":"报告文档已生成"}
```

### 纯前端执行

output_text / ask_question / ask_choice / summary_and_pause / attempt_completion

```json
{"role":"assistant","type":"act","action":"output_text","text":"..."}
```

## observe

LLM 输出的 JSON 对象，格式为 `{"description": "...", "todo": [...]}`。

```json
{"role":"assistant","type":"observe","content":{"description":"...","todo":["..."]}}
```

## 用户反馈

```json
{"role":"user","type":"choice","content":"..."}
{"role":"user","type":"response","content":"..."}
{"role":"user","type":"input","content":"..."}
```