# SSE 事件流

大多数事件包含 `phase` 字段标识当前阶段，前端据此分发显示。**例外**：终态 `{type:"history"}` 事件没有 `phase` 字段（think/action/observe/act 均如此）；文档生成 `/api/generate-document/*` 的各流**不发出** `history` 事件，其完整历史随终态 `done` 的 `conversation_history` 字段下发（只有经 act 的 `generate_document` action 路径才会在末尾补发一条 `history`）；plain-chat `/api/plain-chat/stream/` 的 `chunk`/`done` 也没有 `phase`。

除 `chunk` 外，仅 Think/Action/Observe/Act（explore_* 与代码生成）这些主流程 LLM 流式阶段会发出 `reasoning_chunk` 事件，携带模型推理增量；文档生成（outline/part/unified/YAML outline/from-yaml）、plain-chat 与字段筛选等其余流式调用不发出 `reasoning_chunk`：

```
{phase:"...", type:"reasoning_chunk", content:"模型推理增量..."}   # act 内部还会带 sub_phase
```

`reasoning_chunk` 与 `chunk` 一样仅用于流式临时显示，不写入 `history`。

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

支持单 action 输出 `action_result:{action, ...}` 或多 action 输出 `action_result:{actions:[{action, ...}, ...]}`。可批量组（`_GROUP_1_ACTIONS`）为 `explore_schema`、`explore_functions`、`select_images`，以及按配置启用的 `explore_base_knowledge`、`explore_mcp`；用户交互类（`ask_question`/`ask_choice`/`summary_and_pause`/`attempt_completion`）可批量，其中 summary_and_pause/attempt_completion 必须在最后。两类不可混排，其余 action 只能单次。

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
  ... → {phase:"act", type:"error", sub_phase:"explore_schema", content:"Failed to parse fields after retries; keeping previous selection"}
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

空知识库提前结束（未调用 LLM）：
  {phase:"act", type:"msg",  sub_phase:"explore_base_knowledge", content:"Searching base knowledge..."}
  {phase:"act", type:"done", sub_phase:"explore_base_knowledge", content:"*(No relevant knowledge found)*",
   result:{selected_knowledge_ids:[], knowledge_content:"", summary:""},
   search_keyword:"..."}
  {type:"history", history:[...]}

重试后成功：
  ... → {phase:"act", type:"msg", sub_phase:"explore_base_knowledge", content:"Parsing failed, re-analyzing..."}
  → 重新生成 → {type:"done", ...} → {type:"history", ...}

重试耗尽失败：
  ... → {phase:"act", type:"error", sub_phase:"explore_base_knowledge", content:"Failed to parse knowledge selection after retries; keeping previous selection"}
  （act 阶段随后仍会发出 {type:"history", ...}）
```

### explore_functions

```
成功：
  {phase:"act", type:"msg",    sub_phase:"explore_functions", content:"Searching function information..."}
  {phase:"act", type:"status", sub_phase:"explore_functions", content:"Analyzing required functions..."}
  {phase:"act", type:"chunk",  sub_phase:"explore_functions", content:"..."}  ×N
  {phase:"act", type:"done",   sub_phase:"explore_functions", content:"...",
   result:{selected_functions:[...], func_context:"...", explore_plan:"..."},
   search_keyword:"..."}
  {type:"history", history:[...]}

有效解析但选择为空：
  ... → {phase:"act", type:"done", sub_phase:"explore_functions", content:"*(No functions selected)*",
   result:{selected_functions:[], func_context:"...", explore_plan:"..."}}
  → {type:"history", ...}

重试后成功：
  ... → {phase:"act", type:"msg", sub_phase:"explore_functions", content:"Parsing failed, re-analyzing functions..."}
  → 重新生成 → {type:"done", ...} → {type:"history", ...}

重试耗尽失败：
  ... → {phase:"act", type:"error", sub_phase:"explore_functions", content:"Failed to parse function selection after retries; keeping previous selection"}
  （不再发出 done；blackboard 的 FUNC 区域保持上一次有效选择、不被空列表覆盖；act 条目带
   error:"explore_functions parse failed; previous selection preserved"，随后仍会发出 {type:"history", ...}）
```

> `explore_functions` 与其他 explore_* 一样重试 1 次（共 2 次尝试，重试提示 "Parsing failed, re-analyzing functions..."）。重试耗尽时发出 `error` 事件且**无** `done`，并保留 blackboard 中上一次的函数选择；`content:"*(No functions selected)*"` 只在解析有效但返回空列表时出现。

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
成功（单页/多页统一；多页并行抓取后合并为一段 markdown）：
  {phase:"act", type:"msg",   sub_phase:"fetch_webpage", content:"Fetching N page(s) in parallel..."}
  {phase:"act", type:"chunk", sub_phase:"fetch_webpage", content:"## Page Content (N page(s))..."}
  {phase:"act", type:"done",  sub_phase:"fetch_webpage", content:"...",
   result:{urls:["..."], url:"...", pages:[{url, content, error}, ...], content:"..."}}
  {type:"history", history:[...]}

说明：抓取流程本身不再单独发送 error 事件；单个页面失败时该页在 `pages` 中带 `error`，
并在合并内容中显示 "> Failed: ..."，其余页面照常返回。
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
  # 所有服务器均无工具时，error 内容为二者之一（不是斜杠拼接的单一字符串）：
  {phase:"act", type:"error", sub_phase:"explore_mcp", content:"All MCP servers failed to connect: calculator(...), other(...)"}
  {phase:"act", type:"error", sub_phase:"explore_mcp", content:"No MCP servers provided any tools"}

重试后成功：
  ... → {phase:"act", type:"msg", sub_phase:"explore_mcp", content:"Parsing failed, re-analyzing MCP tools..."}
  → 重新生成 → {type:"done", ...} → {type:"history", ...}

重试耗尽（解析失败，与其它 explore_* 不同）：
  ... → {phase:"act", type:"msg", sub_phase:"explore_mcp", content:"Parsing failed, re-analyzing MCP tools..."}
  → {phase:"act", type:"done", sub_phase:"explore_mcp", content:"*(No tools selected)*",
     result:{selected_tools:[], catalog:"...", explore_plan:""}}
  → {type:"history", history:[...]}
```

> 有失败的服务器时用 `"All MCP servers failed to connect: "` 拼接各服务器名（形如 `name(error)`）；没有任何服务器报告失败（即都连上但都没工具）时用 `"No MCP servers provided any tools"`。
>
> 与 explore_schema / explore_functions / explore_base_knowledge 不同：explore_mcp 解析重试耗尽时**不发 error 事件**，而是照常发出一个 `done`（`content:"*(No tools selected)*"`、`selected_tools:[]`），并用空选择**覆盖**黑板的 MCP 区域（`utils/blackboard.py::_action_region_payload` 的 explore_mcp 分支不检查 parse_failed），即不保留上一次的有效选择。

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
  # 服务器不存在同样走 "MCP call failed"，异常文本为 "MCP server not found: {server}"：
  {phase:"act", type:"error", sub_phase:"exe_mcp", content:"MCP call failed: {server}/{tool}: MCP server not found: {server}"}
  # 整次执行未提供任何工具（既无 tools 数组也无 server/tool）：
  {phase:"act", type:"error", sub_phase:"exe_mcp", content:"MCP tools are required: provide a tools array or server/tool/params fields"}
  # 批量数组中某一项缺少 server 或 tool：
  {phase:"act", type:"error", sub_phase:"exe_mcp", content:"Tool #{i} is missing server or tool name"}
```

### select_images

```
成功：
  {phase:"act", type:"msg",   sub_phase:"select_images", content:"Updating selected images (N)..."}
  {phase:"act", type:"chunk", sub_phase:"select_images", content:"## Selected Images\n\n..."}
  {phase:"act", type:"done",  sub_phase:"select_images", content:"...",
   result:{selected_images:[{path, reason}, ...]}}
  {type:"history", history:[...]}

失败（`images`/`selected_images` 缺失或不是数组）：
  {phase:"act", type:"error", sub_phase:"select_images", content:"select_images requires an `images` array"}
  # 数组非空但没有任何有效条目（每项缺少可用的 path）：
  {phase:"act", type:"error", sub_phase:"select_images", content:"select_images received no valid image entries (each needs a path and reason)"}
  # 两种失败下 act 条目都只带 error 字段（不写 selected_images），随后仍会发出 {type:"history", ...}
```

### 用户交互类（ask_question / ask_choice / summary_and_pause / attempt_completion）

```
  {phase:"act", type:"msg",   sub_phase:"{action}", content:"Presenting {action}..."}
  {phase:"act", type:"chunk", sub_phase:"{action}", content:"{text}"}
  {phase:"act", type:"done",  sub_phase:"{action}", content:"{text}",
   result:{action, text, choices, needs_user_input, paused, completed}}
  {type:"history", history:[...]}
```

> `done.result` 按动作置位交互标记：`needs_user_input`（ask_question / ask_choice）、`paused`（summary_and_pause）、`completed`（attempt_completion），前端据此驱动交互循环；这些动作不调用任何工具/LLM。

### generate_document

```
成功：
  {phase:"act", type:"msg",   sub_phase:"generate_document", content:"Generating report document..."}
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
  # （user_prompt 非空时先发一条：{phase:"yaml_outline", type:"msg", content:"Processing your instructions..."}）
  {phase:"yaml_outline", type:"msg",   content:"Generating YAML outline..."}
  {phase:"yaml_outline", type:"chunk", content:"..."}  ×N
  {phase:"yaml_outline", type:"done",  content:"<YAML string>",
   yaml_file:"outline_{session_id}_{rand}.yaml", yaml_base:"{rand}"}
  {phase:"yaml_outline", type:"error", content:"Failed to generate valid YAML outline after retries"}

  # POST /api/generate-document/stream/from-yaml/ （每节一次请求）
  # Request body 含 section_index, confirmed_sections（前面已确认节的内容让LLM看到）
  {phase:"document_from_yaml", type:"msg",         content:"Generating {N} sections from YAML outline..."}
  {phase:"document_from_yaml", type:"section_msg", content:"Generating section 1/N: {heading}",
   section_index:0, heading:"...", total_sections:N}
  {phase:"document_from_yaml", type:"chunk",       content:"..."}  ×N
  {phase:"document_from_yaml", type:"section_done", content:"...", section_index:0,
   heading:"...", section_file:"draft_{session_id}_{base}_s00.md", total_sections:N}
  # 全篇生成（请求未指定 section_index）完成后追加一条汇总 done：
  {phase:"document_from_yaml", type:"done", content:"<full markdown>", title:"...",
   md_file:"...", section_files:[{name, heading, index}, ...], sections_count:N}
  # 错误（此后流结束）：
  # {phase:"document_from_yaml", type:"error", content:"Failed to parse YAML outline: no sections found"}
  # {phase:"document_from_yaml", type:"error", content:"Invalid section_index: {i}, total: {N}"}
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
  {phase:"act", type:"status", sub_phase:"generate", content:"Generating and executing code..."}
  {phase:"act", type:"msg",   sub_phase:"code", content:"Analyzing question..."}
  {phase:"act", type:"msg",   sub_phase:"code", content:"Generating code..."}
  {phase:"act", type:"chunk", sub_type:"code_chunk",    sub_phase:"code", content:"..."}  ×N
  {phase:"act", type:"reasoning_chunk", sub_phase:"code", content:"..."}  ×N
  {phase:"act", type:"chunk", sub_type:"code_complete", sub_phase:"code", content:"def ..."}
  {phase:"act", type:"chunk", sub_type:"code_gen_error",sub_phase:"code", content:"code generation error"}
  {phase:"act", type:"msg",   sub_phase:"exec", content:"Executing code..."}
  {phase:"act", type:"chunk", sub_type:"exec_chunk",    sub_phase:"exec", content:"..."}  ×N
  {phase:"act", type:"chunk", sub_type:"exec_complete", sub_phase:"exec", content:"...", images:["xxx.png"]}
  {phase:"act", type:"done",  sub_phase:"exec", code:"...", content:"...", images:["xxx.png"],
   result:{code:"...", exec_result:"...", error:null, images:["xxx.png"]}}
  {type:"history", history:[...]}

执行错误后重试成功：
  ... → {sub_type:"code_exe_error", content:"..."}
  → {phase:"act", type:"msg", content:"Execution failed, regenerating code based on error..."}
  → 重新生成并执行 → {type:"done", ...} → {type:"history", ...}

重试耗尽失败：
  ... → {phase:"act", type:"error", content:"generate_and_execute_stream_error"}
```

> 该 action 起始会先发一个 `sub_phase:"generate"` 的 `status` 事件（`content:"Generating and executing code..."`），随后子事件切到 `sub_phase:"code"` / `"exec"`。
> `done` 事件同时带顶层 `images` 与 `result.images` 两个字段。
> 若 act 执行过程中抛出未捕获异常，会发出带 `fatal:true` 的终止错误事件：`{phase:"act", type:"error", content:"Internal error during `{action}`: ...", fatal:true}`，并仍追加一条 `history`。

`exec_complete` / `done` 事件中的 `images` 字段携带本次代码执行生成的图片文件名列表（去重后；本地图片仅存文件名，外部 http 图片保留完整 URL）。前端渲染时拼接 `/tmp_imgs/`；该字段仅用于前端展示，不喂给 LLM。

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
  ... → {phase:"observe", type:"error", sub_phase:"review", content:"Failed to review after retries"}
```

## 说明

- `{type:"history", history:[...]}` 是最后一条事件，包含完整的 `conversation_history`。前端收到后替换本地历史并重建显示。
- `history` 的第一个元素是 blackboard 条目（`type:"blackboard"`），保存完整探索结果；普通 act 条目只保留参数、计划和选中项。前端从该条目读取 Blackboard 弹窗内容。
- `generate_and_execute` 每次执行后会把本次生成的图片列表写入 blackboard 的 `recent_generated_images` 区域（覆盖更新；本地图片通常为文件名，本机静态地址或外部图片为完整 URL），该区域随 `## Blackboard` 段以文本喂给 LLM；模型 `supports_images=true` 且请求 `meta.use_images` 开启时，图片还会作为 `image_url` 内容随请求提交。`act` 条目中的 `images` 字段仅用于前端展示。
- `select_images` 执行后会把 `{"path", "reason"}` 列表整体覆盖写入 blackboard 的 `selected_images` 区域，并返回含 `selected_images` 的 `act` 条目；这些图片会排在上一次代码执行生成的 `images` 之后提交给支持多模态的模型。该 action 属于 Group 1，可与 `explore_*` 在同一次 `actions` 数组中选择。
- 用户上传的图片随本轮第一个请求（Think 模式的 `POST /api/think/stream/`，Chat 模式的 `POST /api/action/stream/`）以 base64 放在 user 条目的 `uploaded` 字段提交，无独立上传接口。请求信封中间件是 `main.py` 的 `unified_request_envelope`（由它调用 `utils/image_ingest.py` 的 `ingest_uploaded_images`；仅在请求同时携带 `meta`(对象) 与 `data` 的 `{meta, data}` 信封时触发），解码保存为 `tmp_imgs/upload_<8位小写字母>.png`，把 `uploaded` 改写为文件名列表，并**追加合并**进 blackboard 的 `selected_images` 区域；处理在路由前完成且幂等，因此该请求的 `## Context` 与随后的 `history` 事件都已是文件名版本。详见 `docs/api.md` 的「用户上传图片」。
- 所有 `chunk` 事件仅用于流式临时显示，最终显示由 `history` 决定。
- 重试次数为 2（首次 + 1 次重试），explore_* 全部如此（含 explore_functions）；YAML Outline 生成也是 2 次重试。
- generate_document_unified 的 done 事件会先发一个仅含 content 的 done，再发一个含完整文件元数据的 done。
- 重试耗尽后是否 yield `history` 取决于阶段：think/action/observe 在重试耗尽时只 yield `error`，**不** yield `history`；而 **act** 无论子步骤是否重试耗尽（包括顶层捕获到未处理异常时发出带 `fatal:true` 的 error），都会继续追加并 yield 一条 `history`。act 的两个例外：action 在配置中被禁用时只发出 `error`（`content:"Action \`{action}\` is not available: ..."`）并直接结束，**不** yield `history`；未知 action 只发出 `error`（`content:"Unknown action: {action}"`），仅当传入的 `conversation_history` 非空时才把原历史原样作为 `history` 事件发出（不落库、无新条目）。
- think/action/observe 顶层捕获到未处理异常时同样发出带 `fatal:true` 的终止 error 事件（`content:"Internal error during \`think\`/\`action\`/\`observe\`: ..."`），其后**没有** `history` 事件（对比：act 的 fatal error 之后仍会追加一条 `history`）。