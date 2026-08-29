# Action 输入输出文档

每个环节记录三项：**输入**（LLM 决策输出的 JSON / API 入参）、**输出**（写入 `conversation_history` 的条目）、**上下文**（`history_to_text` 转换后喂给 LLM 的文本）。

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

**输出**
```json
{"role":"assistant","type":"action_decision","content":{"action":"...", ...}}
```

**上下文**
```
[ACTION] content:
{"action": "...", ...}
```

---

## 3. explore_schema

**输入**
```json
{"action": "explore_schema", "keyword": "..."}
```

**输出**
```json
{"role":"assistant","type":"act","action":"explore_schema","selected_fields":{...},"explore_plan":"...","schema_detail":"...","selected_guides":[...],"query_guide_content":"..."}
```

**上下文**
```
[ACT explore_schema] selected_fields: {"table1":["col1"],...}
[ACT explore_schema] explore_plan:
{plan}
[ACT explore_schema] selected_guides: [1, 3, 7]
[ACT explore_schema] query_guide_content:
{query_guide_content}
[ACT explore_schema] schema_detail:
{schema_detail}
```

---

## 4. explore_functions

**输入**
```json
{"action": "explore_functions", "keyword": "..."}
```

**输出**
```json
{"role":"assistant","type":"act","action":"explore_functions","selected_functions":[...],"func_docs":"..."}
```

**上下文**
```
[ACT explore_functions] selected_functions: ["func1",...]
[ACT explore_functions] func_docs:
{func_docs}
```

---

## 5. generate_and_execute

**输入**
```json
{"action": "generate_and_execute", "funcs": ["exe_sql", ...], "research_guide": "..."}
```

**输出（成功）**
```json
{"role":"assistant","type":"act","action":"generate_and_execute","code":"...","result":"..."}
```

**输出（失败）**
```json
{"role":"assistant","type":"act","action":"generate_and_execute","error":"...","code":"...","result":"..."}
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
```

---

## 14. Observe

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

## 15. 用户反馈

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