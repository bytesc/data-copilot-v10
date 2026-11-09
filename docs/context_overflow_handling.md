# 上下文超长（Context Overflow）处理机制

## 概述

当一次 LLM 请求超过模型的最大上下文长度时，后端会**自动在内存中进一步裁剪上下文并用更高裁剪级别重试**，直到成功或无法再变小为止。该额外裁剪**只在本次请求生效，不写回数据库**——`save_session_step` 仍只持久化 level 0 的 history/trimmed。

核心实现位于 `utils/context_trim.py`，所有 LLM 调用点通过两个包装器接入：

- `stream_with_context_retry(build_prompt, llm, images=None, max_level=4, on_retry=None)`：流式，逐块 `yield (chunk, reasoning)`。
- `call_with_context_retry(build_prompt, llm, images=None, max_level=4, on_retry=None)`：非流式，返回消息对象（内部 `call_llm` 返回 `response.choices[0].message`，取 `.content` 得到文本）。

两者都需要一个 `build_prompt(level) -> str` 闭包：level 决定裁剪强度。

---

## 与常规 Context Trim 的区别

两者共用同一套 `HISTORY_RETENTION` 分类规则和 `trim_conversation_history`，但定位不同：**常规 Context Trim 是每步都做的常态化体积控制；本机制是报错后才触发的兜底重试。** level 0 的裁剪就等于常规 Context Trim，本机制是在它之上的“加码”。

| 维度 | 常规 Context Trim | 上下文超长处理（本机制） |
|---|---|---|
| 触发时机 | 每一步都执行（组装 prompt 前） | 仅在 LLM 返回“超过最大上下文”错误后 |
| 触发依据 | 固定分类保留规则 `HISTORY_RETENTION` | `is_context_length_error(exc)` 判定错误 |
| 目的 | 预防历史无限增长、控制每步体积 | 故障恢复：缩小上下文后重试 |
| 强度 | 单一固定规则（即 level 0） | 分级 level 0→4 逐级收紧 |
| 是否重试 | 否 | 是（`stream/call_with_context_retry`） |
| 是否感知字符/token | 不感知，只按条数 | 按块字符上限 `cap_text` + 条数分级 |
| 对象范围 | 只裁 `conversation_history` | history + blackboard 大字段 + 无 history 调用点的大块 |
| 是否写库 | 写库：`save_session_step` 保存 trim 结果 | 不写库：额外裁剪只在内存 prompt 里 |

要点：

1. **常态化 vs 反应式**：`prepare_trimmed_context(..., level=0)` 与 `save_session_step` 每步都调用；本机制只有 `is_context_length_error` 为真才进入。
2. **同一函数、不同 level**：`trim_conversation_history(history, level)` 常规用 level 0，本机制用 1→4。
3. **只有本机制会“按字符切块”和“动 blackboard”**：常规 Trim 不截断单条内容，也不截断 blackboard 的大字段。
4. **只有本机制覆盖无对话上下文的调用**（`sql_code`、`data_explanation`、`get_function_info`、`plain_chat`、`data_comment`、`llm_predict_hdb`、`base_knowledge` get/set），方式是按块截断。
5. **写库边界**：常规 Trim 结果持久化；本机制 level>0 结果绝不落库，下一轮仍从库里的 level 0 历史重建。

---

## 触发与判定

`is_context_length_error(exc)` 对异常做 best-effort 判定：读取 `str(exc)` 以及 `message/body/code` 属性，按关键字（中英文）匹配，例如：

- `context_length`、`context length`、`context window`
- `maximum context`、`max context`、`maximum number of tokens`、`too many tokens`、`token limit`、`tokens exceed`
- `prompt is too long`、`input is too long`、`request too large`、`reduce the length`
- `上下文长度`、`上下文过长`、`超过最大上下文`、`输入过长`、`长度超`

只有判定为超长错误时才触发重试；其它异常直接抛出。

每次触发重试时，会在命令行打印警告（`_warn_context_retry`）：

```text
[WARNING] LLM context length exceeded; retrying with trim level 2/4 (prompt 123456 -> 45678 chars). detail: ...
```

流式与非流式两条路径都会打印。

重试还会做一次**有效性保护**：若某个更高级别的 `build_prompt(level+1)` 产出的 prompt 没有比上一级更短，则直接抛出原异常，避免用相同/更大的 prompt 反复无效调用。

---

## 分级裁剪规则（level）

level 0 完全等于改动前的行为；level 1→4 逐级收紧。

### 1) 历史条数分级（有 conversation_history 时）

`trim_conversation_history(history, level)` 对每个分类保留最近 N 条：

```
N = min(base_limit, cap, round(base_limit * factor))   # 且不小于 1
```

| level | cap | factor |
|-------|-----|--------|
| 0 | —（用 base） | — |
| 1 | 50 | 0.5 |
| 2 | 12 | 0.25 |
| 3 | 4 | 0.1 |
| 4 | 1 | 0.0 |

- 每个分类至少保留 1 条；`role == "user"` 的条目始终保留。
- `HISTORY_RETENTION` 中标记为“永久保留”（999）的大体量分类（如 `act_result`、`act_exe_mcp`）会被 cap 显著压缩，这是削减历史体积的主要来源。

### 2) 段落字符分级（对 prompt 内嵌大块）

`cap_text(text, level, base_cap=None)` 按 level 设字符上限并截断，截断处追加 `\n...[truncated]`：

| level | 上限（字符） |
|-------|--------------|
| 0 | 无限制 |
| 1 | 80000 |
| 2 | 40000 |
| 3 | 16000 |
| 4 | 6000 |

`base_cap` 可为特定段落设更小的上限。

### 3) Blackboard 分级

`blackboard_to_text(board, level)` / `blackboard_section(history, level)` 在 level>0 时**只截断体积大的自由文本字段**，保留结构化标识字段：

| 区域 | 被截断字段 | 保留字段 |
|------|-----------|----------|
| DB | `query_guide_content`、`schema_detail` | `selected_fields`、`selected_guides`、`explore_plan` |
| FUNC | `func_docs` | `selected_functions` |
| KNOWLEDGE | `knowledge_content` | `selected_knowledge_ids`、`summary` |
| MCP | `tool_detail`、`catalog` | `selected_tools` |

字段上限：20000 / 8000 / 3000 / 1000 字符（level 1→4）。

---

## 情况一：有对话上下文的调用

适用：`think`、`action`、`observe`、`document_generator`（大纲/分节/统一/YAML 四类），以及 `act` 的 `explore_*` 与代码生成。

**措施：优先重裁 `conversation_history`（历史条数分级），同时用分级 blackboard。**

- `build_prompt(level)` 内部用 `prepare_trimmed_context(session_id, history, level=level)` 重建上下文文本，并用 `blackboard_section(history, level=level)` 重建 blackboard 段。
- 各阶段把原来内联的 prompt 提成函数以便按级重建：
  - `agent/think.py` → `_build_think_prompt(context, blackboard_text)`
  - `agent/observe.py` → `_build_observe_prompt(context, blackboard_text)`
  - `agent/action.py` → `_build_action_prompt(..., level)`
  - `agent/act.py` → 子函数接收 `build_question` / `build_blackboard` 闭包
- 代码生成还会额外按块截断：`get_cot_code_prompt` 在 level>0 时对 `function_info` / `database` / `knowledge` / `question` 四个块应用 `cap_text`（`agent/agent.py`）。这属于上方「情况一」有对话上下文的路径；下方情况二表中没有代码生成行。

---

## 情况二：没有对话上下文的调用

这类调用没有 `conversation_history` 可裁，因此对不同调用点采用**按块结构化截断**：只截断体积最大的“数据/知识/结构”块，**绝不截断尾部的指令、输出格式、语言要求**。

| 调用点 | 削减的块 | 方式 |
|--------|----------|------|
| `sql_code.filter_db_fields` / `filter_db_fields_stream` | `_build_filter_prompt(level)` 内截 schema + question | 非流式 / 流式 |
| `data_explanation.get_llm_data_explanation_func` | 只截 `question`；data 已按 `max_length` 采样，不重复采样 | 非流式 |
| `get_function_info.get_function_info` / `filter_functions_stream` | `get_function_prompt(level)` 截 `FUNCTION_DESCRIPTION` + question | 非流式 / 流式 |
| `plain_chat.get_plain_chat` / `get_plain_chat_stream` | 截函数目录 + 库结构 + question | 非流式 / 流式 |
| `data_comment.get_llm_data_comment_func` | 截输入文本 + 表结构 | 非流式 |
| `llm_predict_hdb` | 截 `search_conditions` + `hdb_price_history`（DB 查询结果，最大块） | 非流式 |
| `get_base_knowledge`（5 个 `*_db_llm`） | `_build_knowledge_context(level)` 截 knowledge_text / extra_text / context | 流式 |
| `set_base_knowledge` | 截 existing 知识 + db 结构 + 输入文本 | 非流式 |
| `set_code_guide` / `set_think_guide` | 截 existing 指南 + 输入文本 | 非流式 |

要点：

- **已采样/已切片的数据不再二次采样**（如 `data_explanation` 的采样），避免改变分析语义，只裁文本部分。
- **按块独立截断**，不是“把整个 prompt 砍中间”，因此函数选择类 prompt 的格式约束仍在末尾、不会被切掉。
- level 0 时输出与改动前完全一致。

---

## 不写回数据库

- `save_session_step(session_id, history, new_entries)` 内部只调用 `trim_conversation_history(history)`（level 0）后落库。
- level>0 的额外裁剪只存在于本次重建的 prompt 中，随请求结束即丢弃。

---

## 新增调用点接入方式

1. 把 prompt 构造写成一个依赖 `level` 的函数：

   ```python
   def build_prompt(level):
       return f"...{cap_text(big_section, level)}...{instruction_tail}"
   ```

2. 用包装器发起调用：

   ```python
   # 流式
   for chunk, reasoning in stream_with_context_retry(build_prompt, llm, images=images):
       ...
   # 非流式
   response = call_with_context_retry(build_prompt, llm)
   ```

3. 有 conversation_history 的，用 `prepare_trimmed_context(..., level=level)` + `blackboard_section(history, level=level)`；没有的把各自的“大块”用 `cap_text(..., level)` 包起来。

---

## 验证

- `python -m compileall agent utils main.py front.py` 通过。
- 逐一 import 全部改动模块，无循环导入。
- 单元验证：
  - 超长错误识别（中/英关键字）；
  - 分级裁剪条数（如 `think` 3→2→1，user 消息始终保留）；
  - 流式/非流式按级重试最终成功；
  - prompt 无法再缩小时正确抛出原异常。

---

## 相关文件

- `utils/context_trim.py`：错误判定、分级裁剪、`cap_text`、两个重试包装器。
- `utils/blackboard.py`：`blackboard_to_text(section)` 的分级字段截断。
- `agent/think.py` / `observe.py` / `action.py` / `act.py` / `agent.py` / `document_generator.py` / `plain_chat.py` / `data_comment.py`
- `agent/tools/get_function_info.py`
- `agent/tools/copilot/sql_code.py` / `data_explanation.py`
- `agent/tools/base_knowledge/get_base_knowledge.py` / `set_base_knowledge.py` / `set_code_guide.py` / `set_think_guide.py`
- `agent/tools/llm_analysis/llm_predict_hdb.py`
