# SSE 事件流

## think

```
成功：
  {type:"msg",    content:"正在生成分析计划..."}
  {type:"chunk",  content:"..."}  ×N
  {type:"done",   content:"...", plan_result:{description,todo}}
  {type:"history", history:[...]}

重试后成功：
  {type:"msg",    content:"正在生成分析计划..."}
  {type:"chunk",  content:"..."}  ×N
  {type:"msg",    content:"解析失败，正在重新生成分析计划..."}
  {type:"chunk",  content:"..."}  ×N
  {type:"done",   content:"...", plan_result:{description,todo}}
  {type:"history", history:[...]}

重试耗尽失败：
  {type:"msg",    content:"正在生成分析计划..."}
  {type:"chunk",  content:"..."}  ×N
  {type:"msg",    content:"解析失败，正在重新生成分析计划..."}
  {type:"chunk",  content:"..."}  ×N
  {type:"error",  content:"Failed to generate plan after retries"}
```

## action

```
成功：
  {type:"msg",    content:"正在决策下一步动作..."}
  {type:"chunk",  content:"..."}  ×N
  {type:"done",   content:"...", action_result:{action,text,...}}
  {type:"history", history:[...]}

重试后成功：
  {type:"msg",    content:"正在决策下一步动作..."}
  {type:"chunk",  content:"..."}  ×N
  {type:"msg",    content:"解析失败，正在重新决策..."}
  {type:"chunk",  content:"..."}  ×N
  {type:"done",   content:"...", action_result:{action,text,...}}
  {type:"history", history:[...]}

重试耗尽失败：
  {type:"msg",    content:"正在决策下一步动作..."}
  {type:"chunk",  content:"..."}  ×N
  {type:"msg",    content:"解析失败，正在重新决策..."}
  {type:"chunk",  content:"..."}  ×N
  {type:"error",  content:"Action failed: ..."}
```

## act

### explore_schema

```
成功：
  {type:"msg",    sub_phase:"explore_schema", content:"正在搜索数据库信息..."}
  {type:"msg",    sub_phase:"explore_schema", content:"正在分析所需字段..."}
  {type:"chunk",  sub_phase:"explore_schema", content:"..."}  ×N
  {type:"done",   sub_phase:"explore_schema", content:"...",
   result:{selected_fields:{...}, db_context:"...", explore_plan:"..."}}
  {type:"history", history:[...]}

重试后成功：
  ... → {type:"msg", content:"解析失败，正在重新分析..."} → 重新生成 → {type:"done", ...} → {type:"history", ...}

重试耗尽失败：
  ... → {type:"error", content:"Failed to parse fields after retries"}
```

### explore_functions

```
  {type:"msg",     sub_phase:"explore_functions", content:"正在搜索函数信息..."}
  {type:"status",  sub_phase:"explore_functions", content:"正在分析所需函数..."}
  {type:"chunk",   sub_phase:"explore_functions", content:"..."}  ×N
  {type:"done",    sub_phase:"explore_functions", content:"...",
   result:{selected_functions:[...], func_context:"..."}}
  {type:"history", history:[...]}
```

### generate_document

```
成功：
  {type:"msg",     sub_phase:"generate_document", content:"Generating document..."}
  {type:"chunk",   sub_phase:"generate_document", content:"..."}  ×N
  {type:"done",    sub_phase:"generate_document", content:"...",
   file_name:"...", download_url_md:"...", download_url_docx:"..."}
  {type:"history", history:[...]}
```

### generate_and_execute

```
成功：
  {type:"msg",     sub_phase:"code", content:"正在分析问题..."}
  {type:"msg",     sub_phase:"code", content:"正在生成代码..."}
  {type:"chunk",   sub_type:"code_chunk",     sub_phase:"code", content:"..."}  ×N
  {type:"chunk",   sub_type:"code_complete",  sub_phase:"code", content:"def ..."}
  {type:"msg",     sub_phase:"exec", content:"正在执行代码..."}
  {type:"chunk",   sub_type:"exec_chunk",     sub_phase:"exec", content:"..."}  ×N
  {type:"chunk",   sub_type:"exec_complete",  sub_phase:"exec", content:"..."}
  {type:"done",    sub_phase:"exec", code:"...", content:"...",
   result:{code:"...", exec_result:"...", error:null}}
  {type:"history", history:[...]}

执行错误后重试成功：
  ... → {sub_type:"code_exe_error", content:"..."}
  → {type:"msg", content:"执行出错，正在根据错误信息重新生成代码..."}
  → 重新生成并执行 → {type:"done", ...} → {type:"history", ...}

重试耗尽失败：
  ... → {type:"error", content:"generate_and_execute_stream_error"}
```

## observe

```
成功：
  {type:"status", sub_phase:"review", content:"正在审查执行结果..."}
  {type:"msg",    sub_phase:"review", content:"正在审查执行结果..."}
  {type:"chunk",  content:"..."}  ×N
  {type:"done",   content:"...", plan_result:{description,todo}}
  {type:"history", history:[...]}

重试后成功：
  ... → {type:"msg", content:"解析失败，正在重新审查..."} → 重新生成 → {type:"done", ...} → {type:"history", ...}

重试耗尽失败：
  ... → {type:"error", content:"Failed to review after retries"}
```

## 说明

- `{type:"history", history:[...]}` 是最后一条事件，包含完整的 `conversation_history`。前端收到后替换本地历史并重建显示。
- 所有 `chunk` 事件仅用于流式临时显示，最终显示由 `history` 决定。
- 重试次数为 2（首次 + 1 次重试）。
- 重试耗尽后 yield `error` 事件，不 yield `history`。