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
 "selected_functions":[...],"func_docs":"..."}
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

### web_search

```json
{"role":"assistant","type":"act","action":"web_search",
 "search_result":"格式化后的 markdown 搜索结果字符串",
 "query":"..."}
```

上下文格式:
```
[ACT web_search] search_result:
{search_result}
[ACT web_search] query: {query}
```

### fetch_webpage

```json
{"role":"assistant","type":"act","action":"fetch_webpage",
 "url":"...","page_content":"格式化后的 markdown 页面内容字符串"}
```

上下文格式:
```
[ACT fetch_webpage] page_content:
{page_content}
[ACT fetch_webpage] url: {url}
```

### generate_document

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