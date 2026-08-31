# SSE 事件流

所有事件均包含 `phase` 字段标识当前阶段，前端据此分发显示。

## think

```
成功：
  {phase:"think", type:"msg",    content:"正在生成分析计划..."}
  {phase:"think", type:"chunk",  content:"..."}  ×N
  {phase:"think", type:"done",   content:"...", plan_result:{description,todo}}
  {type:"history", history:[...]}

重试后成功：
  {phase:"think", type:"msg",    content:"正在生成分析计划..."}
  {phase:"think", type:"chunk",  content:"..."}  ×N
  {phase:"think", type:"msg",    content:"解析失败，正在重新生成分析计划..."}
  {phase:"think", type:"chunk",  content:"..."}  ×N
  {phase:"think", type:"done",   content:"...", plan_result:{description,todo}}
  {type:"history", history:[...]}

重试耗尽失败：
  {phase:"think", type:"msg",    content:"正在生成分析计划..."}
  {phase:"think", type:"chunk",  content:"..."}  ×N
  {phase:"think", type:"msg",    content:"解析失败，正在重新生成分析计划..."}
  {phase:"think", type:"chunk",  content:"..."}  ×N
  {phase:"think", type:"error",  content:"Failed to generate plan after retries"}
```

## action

```
成功：
  {phase:"action", type:"msg",    content:"正在决策下一步动作..."}
  {phase:"action", type:"chunk",  content:"..."}  ×N
  {phase:"action", type:"done",   content:"...", action_result:{action,text,...}}
  {type:"history", history:[...]}

重试后成功：
  {phase:"action", type:"msg",    content:"正在决策下一步动作..."}
  {phase:"action", type:"chunk",  content:"..."}  ×N
  {phase:"action", type:"msg",    content:"解析失败，正在重新决策..."}
  {phase:"action", type:"chunk",  content:"..."}  ×N
  {phase:"action", type:"done",   content:"...", action_result:{action,text,...}}
  {type:"history", history:[...]}

重试耗尽失败：
  {phase:"action", type:"msg",    content:"正在决策下一步动作..."}
  {phase:"action", type:"chunk",  content:"..."}  ×N
  {phase:"action", type:"msg",    content:"解析失败，正在重新决策..."}
  {phase:"action", type:"chunk",  content:"..."}  ×N
  {phase:"action", type:"error",  content:"Action failed: ..."}
```

## act

### explore_schema

```
成功：
  {phase:"act", type:"msg",    sub_phase:"explore_schema", content:"正在搜索数据库信息..."}
  {phase:"act", type:"msg",    sub_phase:"explore_schema", content:"正在分析所需字段..."}
  {phase:"act", type:"chunk",  sub_phase:"explore_schema", content:"..."}  ×N
  {phase:"act", type:"done",   sub_phase:"explore_schema", content:"...",
   result:{selected_fields:{...}, db_context:"...", explore_plan:"...",
           selected_guides:[1,3], query_guide_content:"..."},
   search_keyword:"..."}
  {type:"history", history:[...]}

重试后成功：
  ... → {phase:"act", type:"msg", sub_phase:"explore_schema", content:"解析失败，正在重新分析..."}
  → 重新生成 → {type:"done", ...} → {type:"history", ...}

重试耗尽失败：
  ... → {phase:"act", type:"error", sub_phase:"explore_schema", content:"Failed to parse fields after retries"}
```

### explore_base_knowledge

```
成功：
  {phase:"act", type:"msg",    sub_phase:"explore_base_knowledge", content:"正在搜索基础知识..."}
  {phase:"act", type:"msg",    sub_phase:"explore_base_knowledge", content:"正在分析相关知识..."}
  {phase:"act", type:"chunk",  sub_phase:"explore_base_knowledge", content:"..."}  ×N
  {phase:"act", type:"done",   sub_phase:"explore_base_knowledge", content:"...",
   result:{selected_knowledge_ids:[1,3,7], knowledge_content:"...", summary:"..."},
   search_keyword:"..."}
  {type:"history", history:[...]}

重试后成功：
  ... → {phase:"act", type:"msg", sub_phase:"explore_base_knowledge", content:"解析失败，正在重新分析..."}
  → 重新生成 → {type:"done", ...} → {type:"history", ...}

重试耗尽失败：
  ... → {phase:"act", type:"error", sub_phase:"explore_base_knowledge", content:"Failed to parse knowledge selection after retries"}
```

### explore_functions

```
成功：
  {phase:"act", type:"msg",    sub_phase:"explore_functions", content:"正在搜索函数信息..."}
  {phase:"act", type:"status", sub_phase:"explore_functions", content:"正在分析所需函数..."}
  {phase:"act", type:"chunk",  sub_phase:"explore_functions", content:"..."}  ×N
  {phase:"act", type:"done",   sub_phase:"explore_functions", content:"...",
   result:{selected_functions:[...], func_context:"..."},
   search_keyword:"..."}
  {type:"history", history:[...]}
```

### web_search

```
成功：
  {phase:"act", type:"msg",   sub_phase:"web_search", content:"正在搜索: {query}..."}
  {phase:"act", type:"chunk", sub_phase:"web_search", content:"搜索结果 markdown..."}
  {phase:"act", type:"done",  sub_phase:"web_search", content:"...",
   result:{search_results:{query,count,results:[{title,url,snippet}]}, query:"..."}}
  {type:"history", history:[...]}

失败：
  {phase:"act", type:"error", sub_phase:"web_search", content:"搜索失败: ..."}
```

### fetch_webpage

```
成功：
  {phase:"act", type:"msg",   sub_phase:"fetch_webpage", content:"正在获取页面: {url}..."}
  {phase:"act", type:"chunk", sub_phase:"fetch_webpage", content:"页面内容 markdown..."}
  {phase:"act", type:"done",  sub_phase:"fetch_webpage", content:"...",
   result:{url:"...", content:"..."}}
  {type:"history", history:[...]}

失败：
  {phase:"act", type:"error", sub_phase:"fetch_webpage", content:"获取页面失败: ..."}
```

### generate_document

```
成功：
  {phase:"act", type:"msg",   sub_phase:"generate_document", content:"正在生成报告文档..."}
  # 内部事件流（来自 document_generator.py）：
  # 分步模式（_event_stream_generate_document）：
  {phase:"outline", type:"msg",   content:"Generating document outline..."}
  {phase:"outline", type:"chunk", content:"..."}  ×N
  {phase:"outline", type:"done",  content:"...", outline:{title,parts:[{heading,description}]}}
  {phase:"part",    type:"msg",   content:"Generating part 1/N: {heading}", part_index:0, heading:"..."}
  {phase:"part",    type:"chunk", content:"..."}  ×N
  {phase:"part",    type:"done",  content:"...", part_index:0, heading:"..."}
  ...（重复 N 次）
  {phase:"document", type:"done", content:"...", title:"...", parts_count:N,
   file_name:"doc_xxxx", download_url_md:"...", download_url_docx:"...",
   download_url_pdf:"...", conversation_history:[...]}

  # 统一模式（_event_stream_generate_document_unified）：
  {phase:"act", sub_phase:"generate_document", type:"msg",   content:"Generating document..."}
  {phase:"act", sub_phase:"generate_document", type:"chunk", content:"..."}  ×N
  {phase:"act", sub_phase:"generate_document", type:"done",  content:"...",
   title:"...", file_name:"doc_xxxx", download_url_md:"...",
   download_url_docx:"...", download_url_pdf:"...", conversation_history:[...]}

  {type:"history", history:[...]}
```

### generate_and_execute

```
成功：
  {phase:"act", type:"msg",   sub_phase:"code", content:"正在分析问题..."}
  {phase:"act", type:"msg",   sub_phase:"code", content:"正在生成代码..."}
  {phase:"act", type:"chunk", sub_type:"code_chunk",    sub_phase:"code", content:"..."}  ×N
  {phase:"act", type:"chunk", sub_type:"code_complete", sub_phase:"code", content:"def ..."}
  {phase:"act", type:"msg",   sub_phase:"exec", content:"正在执行代码..."}
  {phase:"act", type:"chunk", sub_type:"exec_chunk",    sub_phase:"exec", content:"..."}  ×N
  {phase:"act", type:"chunk", sub_type:"exec_complete", sub_phase:"exec", content:"..."}
  {phase:"act", type:"done",  sub_phase:"exec", code:"...", content:"...",
   result:{code:"...", exec_result:"...", error:null}}
  {type:"history", history:[...]}

执行错误后重试成功：
  ... → {sub_type:"code_exe_error", content:"..."}
  → {phase:"act", type:"msg", content:"执行出错，正在根据错误信息重新生成代码..."}
  → 重新生成并执行 → {type:"done", ...} → {type:"history", ...}

重试耗尽失败：
  ... → {phase:"act", type:"error", content:"generate_and_execute_stream_error"}
```

## observe

```
成功：
  {phase:"observe", type:"status", sub_phase:"review", content:"正在审查执行结果..."}
  {phase:"observe", type:"msg",    sub_phase:"review", content:"正在审查执行结果..."}
  {phase:"observe", type:"chunk",  content:"..."}  ×N
  {phase:"observe", type:"done",   content:"...", plan_result:{description,todo}}
  {type:"history", history:[...]}

重试后成功：
  ... → {phase:"observe", type:"msg", content:"解析失败，正在重新审查..."} → 重新生成 → {type:"done", ...} → {type:"history", ...}

重试耗尽失败：
  ... → {phase:"observe", type:"error", content:"Failed to review after retries"}
```

## 说明

- `{type:"history", history:[...]}` 是最后一条事件，包含完整的 `conversation_history`。前端收到后替换本地历史并重建显示。
- 所有 `chunk` 事件仅用于流式临时显示，最终显示由 `history` 决定。
- 重试次数为 2（首次 + 1 次重试）。
- 重试耗尽后 yield `error` 事件，不 yield `history`。