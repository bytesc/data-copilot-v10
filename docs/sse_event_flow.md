# SSE 事件流

所有事件均包含 `phase` 字段标识当前阶段，前端据此分发显示。

## think

```
成功：
  {phase:"think", type:"msg",    content:"Generating analysis plan..."}
  {phase:"think", type:"chunk",  content:"..."}  ×N
  {phase:"think", type:"done",   content:"...", plan_result:{description,todo}}
  {type:"history", history:[...]}

重试后成功：
  {phase:"think", type:"msg",    content:"Generating analysis plan..."}
  {phase:"think", type:"chunk",  content:"..."}  ×N
  {phase:"think", type:"msg",    content:"Parsing failed, regenerating analysis plan..."}
  {phase:"think", type:"chunk",  content:"..."}  ×N
  {phase:"think", type:"done",   content:"...", plan_result:{description,todo}}
  {type:"history", history:[...]}

重试耗尽失败：
  {phase:"think", type:"msg",    content:"Generating analysis plan..."}
  {phase:"think", type:"chunk",  content:"..."}  ×N
  {phase:"think", type:"msg",    content:"Parsing failed, regenerating analysis plan..."}
  {phase:"think", type:"chunk",  content:"..."}  ×N
  {phase:"think", type:"error",  content:"Failed to generate plan after retries"}
```

## action

支持单 action 输出 `action_result:{action, ...}` 或多 action 输出 `action_result:{actions:[{action, ...}, ...]}`。Explore 类（explore_schema/functions/base_knowledge）可批量；用户交互类（output_text/ask_question/ask_choice/summary_and_pause/attempt_completion）可批量，其中 summary_and_pause/attempt_completion 必须在最后。两类不可混排，其余 action 只能单次。

```
成功：
  {phase:"action", type:"msg",    content:"Deciding next action..."}
  {phase:"action", type:"chunk",  content:"..."}  ×N
  {phase:"action", type:"done",   content:"...", action_result:{action,text,...}}
  {type:"history", history:[...]}

多 action 成功：
  {phase:"action", type:"msg",    content:"Deciding next action..."}
  {phase:"action", type:"chunk",  content:"..."}  ×N
  {phase:"action", type:"done",   content:"...", action_result:{actions:[{action:"explore_schema"},{action:"explore_functions"}]}}
  {type:"history", history:[...]}

重试后成功：
  {phase:"action", type:"msg",    content:"Deciding next action..."}
  {phase:"action", type:"chunk",  content:"..."}  ×N
  {phase:"action", type:"msg",    content:"Parsing failed, re-deciding next action..."}
  {phase:"action", type:"chunk",  content:"..."}  ×N
  {phase:"action", type:"done",   content:"...", action_result:{action,text,...}}
  {type:"history", history:[...]}

重试耗尽失败：
  {phase:"action", type:"msg",    content:"Deciding next action..."}
  {phase:"action", type:"chunk",  content:"..."}  ×N
  {phase:"action", type:"msg",    content:"Parsing failed, re-deciding next action..."}
  {phase:"action", type:"chunk",  content:"..."}  ×N
  {phase:"action", type:"error",  content:"Action failed: ..."}
```

## act

### explore_schema

```
成功：
  {phase:"act", type:"msg",    sub_phase:"explore_schema", content:"Searching database information..."}
  {phase:"act", type:"msg",    sub_phase:"explore_schema", content:"Analyzing required fields..."}
  {phase:"act", type:"chunk",  sub_phase:"explore_schema", content:"..."}  ×N
  {phase:"act", type:"done",   sub_phase:"explore_schema", content:"...",
   result:{selected_fields:{...}, db_context:"...", explore_plan:"...",
           selected_guides:[1,3], query_guide_content:"..."},
   search_keyword:"..."}
  {type:"history", history:[...]}

重试后成功：
  ... → {phase:"act", type:"msg", sub_phase:"explore_schema", content:"Parsing failed, re-analyzing..."}
  → 重新生成 → {type:"done", ...} → {type:"history", ...}

重试耗尽失败：
  ... → {phase:"act", type:"error", sub_phase:"explore_schema", content:"Failed to parse fields after retries"}
```

### explore_base_knowledge

```
成功：
  {phase:"act", type:"msg",    sub_phase:"explore_base_knowledge", content:"Searching base knowledge..."}
  {phase:"act", type:"msg",    sub_phase:"explore_base_knowledge", content:"Analyzing relevant knowledge..."}
  {phase:"act", type:"chunk",  sub_phase:"explore_base_knowledge", content:"..."}  ×N
  {phase:"act", type:"done",   sub_phase:"explore_base_knowledge", content:"...",
   result:{selected_knowledge_ids:[1,3,7], knowledge_content:"...", summary:"..."},
   search_keyword:"..."}
  {type:"history", history:[...]}

重试后成功：
  ... → {phase:"act", type:"msg", sub_phase:"explore_base_knowledge", content:"Parsing failed, re-analyzing..."}
  → 重新生成 → {type:"done", ...} → {type:"history", ...}

重试耗尽失败：
  ... → {phase:"act", type:"error", sub_phase:"explore_base_knowledge", content:"Failed to parse knowledge selection after retries"}
```

### explore_functions

```
成功（无重试）：
  {phase:"act", type:"msg",    sub_phase:"explore_functions", content:"Searching function information..."}
  {phase:"act", type:"status", sub_phase:"explore_functions", content:"Analyzing required functions..."}
  {phase:"act", type:"chunk",  sub_phase:"explore_functions", content:"..."}  ×N
  {phase:"act", type:"done",   sub_phase:"explore_functions", content:"...",
   result:{selected_functions:[...], func_context:"..."},
   search_keyword:"..."}
```

### web_search

```
成功：
  {phase:"act", type:"msg",   sub_phase:"web_search", content:"Searching: {query}..."}
  {phase:"act", type:"chunk", sub_phase:"web_search", content:"搜索结果 markdown..."}
  {phase:"act", type:"done",  sub_phase:"web_search", content:"...",
   result:{search_results:{query,count,results:[{title,url,snippet}]}, query:"..."}}
  {type:"history", history:[...]}

失败：
  {phase:"act", type:"error", sub_phase:"web_search", content:"Search failed: ..."}
```

### fetch_webpage

```
成功：
  {phase:"act", type:"msg",   sub_phase:"fetch_webpage", content:"Fetching page: {url}..."}
  {phase:"act", type:"chunk", sub_phase:"fetch_webpage", content:"页面内容 markdown..."}
  {phase:"act", type:"done",  sub_phase:"fetch_webpage", content:"...",
   result:{url:"...", content:"..."}}
  {type:"history", history:[...]}

失败：
  {phase:"act", type:"error", sub_phase:"fetch_webpage", content:"Fetch page failed: ..."}
```

### explore_mcp

```
成功：
  {phase:"act", type:"msg",   sub_phase:"explore_mcp", content:"Connecting to MCP servers to fetch tool list..."}
  {phase:"act", type:"msg",   sub_phase:"explore_mcp", content:"Listing tools from MCP server: calculator..."}
  {phase:"act", type:"msg",   sub_phase:"explore_mcp", content:"Found 8 tools from calculator"}
  {phase:"act", type:"msg",   sub_phase:"explore_mcp", content:"Analyzing required MCP tools..."}
  {phase:"act", type:"chunk", sub_phase:"explore_mcp", content:"..."}  ×N
  {phase:"act", type:"done",  sub_phase:"explore_mcp", content:"...",
   result:{selected_tools:[{server, name}, ...], catalog:"...", explore_plan:"..."},
   search_keyword:"..."}
  {type:"history", history:[...]}

失败：
  {phase:"act", type:"msg",   sub_phase:"explore_mcp", content:"Failed to connect to calculator: ..."}
  {phase:"act", type:"msg",   sub_phase:"explore_mcp", content:"No tools available from calculator"}
  {phase:"act", type:"error", sub_phase:"explore_mcp", content:"No MCP servers configured"}
  {phase:"act", type:"error", sub_phase:"explore_mcp", content:"All MCP servers failed to connect / No MCP servers provided any tools"}
```

### exe_mcp

```
成功（单工具）：
  {phase:"act", type:"msg",   sub_phase:"exe_mcp", content:"Executing MCP tool [1/1]: calculator/calculate..."}
  {phase:"act", type:"msg",   sub_phase:"exe_mcp", content:"Calling calculate..."}
  {phase:"act", type:"chunk", sub_phase:"exe_mcp", content:"### calculator/calculate\n\n..."}
  {phase:"act", type:"done",  sub_phase:"exe_mcp", content:"## MCP Tool Execution Results\n\n...",
   result:{results:[{server:"calculator",tool:"calculate",result:{...}}], combined_display:"..."}}
  {type:"history", history:[...]}

成功（多工具）：
  {phase:"act", type:"msg",   sub_phase:"exe_mcp", content:"Executing MCP tool [1/2]: calculator/add..."}
  {phase:"act", type:"chunk", sub_phase:"exe_mcp", content:"### calculator/add\n\n..."}
  {phase:"act", type:"msg",   sub_phase:"exe_mcp", content:"Executing MCP tool [2/2]: calculator/multiply..."}
  {phase:"act", type:"chunk", sub_phase:"exe_mcp", content:"### calculator/multiply\n\n..."}
  {phase:"act", type:"done",  sub_phase:"exe_mcp", content:"## MCP Tool Execution Results\n\n...",
   result:{results:[{server:"calculator",tool:"add",result:{...}},{server:"calculator",tool:"multiply",result:{...}}], combined_display:"..."}}
  {type:"history", history:[...]}

失败：
  {phase:"act", type:"error", sub_phase:"exe_mcp", content:"MCP call failed: calculator/calculate: ..."}
  {phase:"act", type:"error", sub_phase:"exe_mcp", content:"MCP server not found: server_name"}
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

  # YAML Outline 模式 — 每节单独请求，用户逐节确认
  # POST /api/generate-document/generate-yaml-outline/
  {phase:"yaml_outline", type:"msg",   content:"Generating YAML outline..."}
  {phase:"yaml_outline", type:"chunk", content:"..."}  ×N
  {phase:"yaml_outline", type:"done",  content:"<YAML string>",
   yaml_file:"outline_{session_id}_{rand}.yaml", yaml_base:"{rand}"}

  # POST /api/generate-document/stream/from-yaml/ （每节一次请求）
  # Request body 含 section_index, confirmed_sections（前面已确认节的内容让LLM看到）
  {phase:"document_from_yaml", type:"msg",         content:"Generating..."}
  {phase:"document_from_yaml", type:"section_msg", content:"Generating section 1/N: {heading}",
   section_index:0, heading:"...", total_sections:N}
  {phase:"document_from_yaml", type:"chunk",       content:"..."}  ×N
  {phase:"document_from_yaml", type:"section_done", content:"...", section_index:0,
   heading:"...", section_file:"draft_{session_id}_{base}_s00.md", total_sections:N}
  # 前端显示 textarea，用户编辑后点 Confirm & Next → 下一节 (section_index+1)

  # POST /api/generate-document/yaml-to-prompt/ （非SSE，普通 JSON 请求）
  # Request:  { yaml_content: string }
  # Response: { prompt: string }
  # 后端用 YAML_TO_CHAT_PROMPT 模板拼装英文指令 + YAML，前端通过 submitNewQuestion() 发给主 LLM

  # POST /api/generate-document/finalize/
  {phase:"finalize", type:"done", content:"<full markdown>", title:"...",
   file_name:"doc_xxxx", download_url_md:"...", download_url_docx:"...", download_url_pdf:"..."}

  {type:"history", history:[...]}
```

### generate_and_execute

```
成功：
  {phase:"act", type:"msg",   sub_phase:"code", content:"Analyzing question..."}
  {phase:"act", type:"msg",   sub_phase:"code", content:"Generating code..."}
  {phase:"act", type:"chunk", sub_type:"code_chunk",    sub_phase:"code", content:"..."}  ×N
  {phase:"act", type:"chunk", sub_type:"code_complete", sub_phase:"code", content:"def ..."}
  {phase:"act", type:"chunk", sub_type:"code_gen_error",sub_phase:"code", content:"code generation error"}
  {phase:"act", type:"msg",   sub_phase:"exec", content:"Executing code..."}
  {phase:"act", type:"chunk", sub_type:"exec_chunk",    sub_phase:"exec", content:"..."}  ×N
  {phase:"act", type:"chunk", sub_type:"exec_complete", sub_phase:"exec", content:"..."}
  {phase:"act", type:"done",  sub_phase:"exec", code:"...", content:"...",
   result:{code:"...", exec_result:"...", error:null}}
  {type:"history", history:[...]}

执行错误后重试成功：
  ... → {sub_type:"code_exe_error", content:"..."}
  → {phase:"act", type:"msg", content:"Execution failed, regenerating code based on error..."}
  → 重新生成并执行 → {type:"done", ...} → {type:"history", ...}

重试耗尽失败：
  ... → {phase:"act", type:"error", content:"generate_and_execute_stream_error"}
```

## observe

```
成功：
  {phase:"observe", type:"status", sub_phase:"review", content:"Reviewing execution results..."}
  {phase:"observe", type:"msg",    sub_phase:"review", content:"Reviewing execution results..."}
  {phase:"observe", type:"chunk",  content:"..."}  ×N
  {phase:"observe", type:"done",   content:"...", plan_result:{description,todo}}
  {type:"history", history:[...]}

重试后成功：
  ... → {phase:"observe", type:"msg", content:"Parsing failed, re-reviewing execution results..."} → 重新生成 → {type:"done", ...} → {type:"history", ...}

重试耗尽失败：
  ... → {phase:"observe", type:"error", content:"Failed to review after retries"}
```

## 说明

- `{type:"history", history:[...]}` 是最后一条事件，包含完整的 `conversation_history`。前端收到后替换本地历史并重建显示。
- 所有 `chunk` 事件仅用于流式临时显示，最终显示由 `history` 决定。
- 重试次数为 2（首次 + 1 次重试）。explore_functions 无重试；YAML Outline 生成也有 2 次重试。
- generate_document_unified 的 done 事件会先发一个仅含 content 的 done，再发一个含完整文件元数据的 done。
- 重试耗尽后 yield `error` 事件，不 yield `history`。