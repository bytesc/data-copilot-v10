# 文档生成系统

三种模式，输出 `.md` / `.docx` / `.pdf`。

---

## 模式对比

| | Generate Report (📄) | Generate Document (📋) | YAML Outline (📐) |
|---|---|---|---|
| 按钮 | RightPanel | RightPanel | RightPanel |
| 后端 | `POST /api/generate-document/stream/` | `POST /api/generate-document/stream/unified/` | 三步：① outline ② from-yaml ③ finalize |
| LLM | 2轮：大纲JSON → 逐节 | 1轮：整篇 | 2轮：YAML → 逐节 |
| 人工干预 | 无 | 无 | ✅ 编辑YAML + 逐节确认 |
| SSE | `outline` → `part`×N → `document` | `act(sub_phase:generate_document)` 单段 | `yaml_outline` → `document_from_yaml(section_msg/section_done)` → `finalize` |
| 图片去重 | ✅ | ❌ | ✅ |
| 适用 | 长报告逐步生成 | 快速一次性 | 需用户审核大纲/每节内容 |

---

## YAML Outline 模式 — 接口流程

### 1. 弹窗打开（恢复面板）

```
GET /api/doc-workspace/files/
```
返回 `doc_workspace/` 下所有 `.yaml` 文件。

### 2. 点击 YAML 文件恢复

```
GET /api/doc-workspace/file/outline_{session_id}_{base}.yaml
→ 返回 YAML 内容
```
前端从文件名提取 `base_full = {session_id}_{base}`，按优先级恢复：
1. `GET /api/doc-workspace/file/draft_{base_full}.md` → **200** → 解析章节，跳转 **review**
2. 无合并稿，逐文件请求 `GET /api/doc-workspace/file/draft_{base_full}_s00.md`、`s01.md`... → **有文件** → 恢复已确认节，跳转 **sections**（最后一节可编辑）
3. 都 **404** → 跳转 **YAML 编辑**

### 3. 生成 YAML 大纲

```
POST /api/generate-document/generate-yaml-outline/
Body: { conversation_history, session_id }
```
SSE: `yaml_outline: msg → chunk×N → done { content, yaml_base, yaml_file }`

保存 `outline_{session_id}_{yaml_base}.yaml`。

**YAML 格式定义**:
```yaml
title: "文档标题"                      # 文档标题
sections:                             # 章节列表
  - heading: "1. 章节标题"             # 章节标题（可带编号）
    description: "章节描述"            # 章节内容简述
    subsections:                      # 子节列表（可选）
      - heading: "1.1 子节标题"        # 子节标题
        description: "子节描述"        # 子节内容简述
```

### 4. 逐节生成（每节一次请求）

```
POST /api/generate-document/stream/from-yaml/
Body: {
  conversation_history, yaml_outline, session_id,
  yaml_base, section_index: N,
  confirmed_sections: [{ heading, content }, ...]  // 前面已确认节的内容
}
```
SSE: `msg → section_msg → chunk×N → section_done { content, section_file, total_sections }`

`confirmed_sections` 让 LLM 看到前面节的内容，避免重复。每节即时保存 `draft_{session_id}_{base}_sNN.md`。

### 5. 最终输出

```
POST /api/generate-document/finalize/
Body: { markdown_content, session_id, yaml_base, conversation_history }
```
SSE: `finalize: done { download_url_md/docx/pdf }`

保存 `doc_xxx.md/.docx/.pdf` 到 `tmp_imgs/`，写入 `report_generation_log` 表供 RightPanel 显示。自动清理 `doc_workspace/` 中对应的 `outline_{sid}_{base}.yaml`、`draft_{sid}_{base}.md`、`draft_{sid}_{base}_s*.md`。

### 6. 关闭弹窗

前端仅关闭弹窗，无后端调用。清理已在 finalize 后端完成。

## observe_cycle_log 记录

| 模式 | 函数 | 笔数 | cycle_index | sub_phase |
|------|------|------|-------------|-----------|
| Generate Report | `_event_stream_generate_document` | 1 + N | 0=outline, 1..N=part | outline, part |
| Generate Document | `_event_stream_generate_document_unified` | 1 | 0 | full |
| YAML Outline | `_event_stream_generate_yaml_outline` | 1 | 0 | outline |
| | `_event_stream_generate_from_yaml` | N | 1..N | part |
| | `_event_stream_finalize` | 0 | — | — |

## 上下文记录

三种模式均**不将文档生成过程追加到 conversation_history**。done event 返回的 `conversation_history` 是原始输入的原样回传，不包含文档生成消息。

---

## 文件存储

| 路径 | 内容 | 命名 | Git |
|------|------|------|-----|
| `doc_workspace/` | YAML 大纲 | `outline_{session_id}_{rand8}.yaml` | ❌ |
| `doc_workspace/` | 单节草稿 | `draft_{session_id}_{base}_sNN.md` | ❌ |
| `doc_workspace/` | 合并草稿 | `draft_{session_id}_{base}.md` | ❌ |
| `tmp_imgs/` | 最终文档 | `doc_{rand8}.md/.docx/.pdf` | ❌ |

`doc_workspace/.gitkeep` 保留在 git 中。

---

## 前端组件

| 组件 | 路径 | 说明 |
|------|------|------|
| `YamlOutlineModal.vue` | `vue-front/src/components/YamlOutlineModal.vue` | 三步流程：YAML编辑 → 逐节确认 → review/finalize |
| `RightPanel.vue` | `vue-front/src/components/RightPanel.vue` | 三个按钮入口 |
| `useChat.js` | `vue-front/src/composables/useChat.js` | `fetchGeneratedFilesForSession()` 刷新文件列表 |

---

## 后端核心文件

| 文件 | 说明 |
|------|------|
| `agent/document_generator.py` | 所有文档生成逻辑：prompt、SSE 流、文件转换 |
| `data_access/report_log.py` | 文档日志（`report_generation_log` 表） |