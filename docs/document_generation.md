# 文档生成系统

系统提供三种文档生成模式，均可输出 `.md`、`.docx`、`.pdf` 三种格式。

---

## 模式对比

| | Generate Report（📄） | Generate Document（📋） | YAML Outline（📐） |
|---|---|---|---|
| **按钮位置** | RightPanel | RightPanel | RightPanel |
| **后端端点** | `POST /api/generate-document/stream/` | `POST /api/generate-document/stream/unified/` | 三步：① `generate-yaml-outline/` ② `stream/from-yaml/` ③ `finalize/` |
| **LLM 调用** | 两轮：先大纲 JSON → 逐节生成正文 | 一轮：整篇一次性生成 | 两轮：先 YAML 大纲 → 逐节生成正文 |
| **人工干预** | 无 | 无 | ✅ 可编辑 YAML 大纲 + 可编辑 Markdown 草稿 |
| **SSE 流程** | `outline` → `part` × N → `document` | `act(sub_phase:generate_document)` 单段流式 | `yaml_outline` → `document_from_yaml(section_msg/section_done)` → `finalize` |
| **文档结构** | 编号章节，H3 封顶 | 结论先行，无标题深度限制 | 由 YAML 大纲完全定义 |
| **图片去重** | ✅ 跨章节去重 | ❌ 不涉及 | ✅ 跨章节去重 |
| **适用场景** | 长文报告，逐步生成体验好 | 快速一次性出完整文档 | 需要用户审核和修改大纲/内容的场景 |

---

## 三步流程详解（YAML Outline 模式）

### Step 1: 生成 YAML 大纲

**端点**: `POST /api/generate-document/generate-yaml-outline/`

**请求**:
```json
{
  "conversation_history": [{...}],
  "session_id": "20260922xxxxxx"
}
```

**SSE 事件流**:
```
{phase:"yaml_outline", type:"msg",   content:"Generating YAML outline..."}
{phase:"yaml_outline", type:"chunk", content:"..."}  ×N
{phase:"yaml_outline", type:"done",  content:"<实际 YAML 文本>",
 yaml_file:"outline_xxxx.yaml"}
```

YAML 文件自动保存到 `doc_workspace/outline_xxxx.yaml`。前端展示 YAML 文本供用户编辑。

**YAML 格式**:
```yaml
title: "Document Title"
sections:
  - heading: "1. Section Heading"
    description: "Brief description"
    subsections:
      - heading: "1.1 Subsection Heading"
        description: "Brief description"
```

### Step 2: 生成 Markdown 草稿

**端点**: `POST /api/generate-document/stream/from-yaml/`

**请求**:
```json
{
  "conversation_history": [{...}],
  "yaml_outline": "title: ...\nsections:\n  ...",
  "session_id": "20260922xxxxxx"
}
```

**SSE 事件流**:
```
{phase:"document_from_yaml", type:"msg",         content:"Generating N sections from YAML outline..."}
{phase:"document_from_yaml", type:"section_msg", content:"Generating section 1/N: 1. Market Overview", section_index:0, heading:"1. Market Overview"}
{phase:"document_from_yaml", type:"chunk",       content:"..."}  ×N
{phase:"document_from_yaml", type:"section_done", content:"...", section_index:0, heading:"1. Market Overview"}
...（重复 N 次，图片跨节去重）
{phase:"document_from_yaml", type:"done", content:"<完整 Markdown 文本>",
 title:"...", md_file:"draft_xxxx.md", sections_count:N}
```

Markdown 文件自动保存到 `doc_workspace/draft_xxxx.md`。前端逐节 streaming 展示，完成后显示可编辑的 textarea。

### Step 3: 最终输出

**端点**: `POST /api/generate-document/finalize/`

**请求**:
```json
{
  "markdown_content": "# Title\n\n...（用户可能编辑后的 Markdown）",
  "session_id": "20260922xxxxxx"
}
```

**SSE 事件流**:
```
{phase:"finalize", type:"done", content:"<完整 Markdown>", title:"...",
 file_name:"doc_xxxx",
 download_url_md:"http://.../tmp_imgs/doc_xxxx.md",
 download_url_docx:"http://.../tmp_imgs/doc_xxxx.docx",
 download_url_pdf:"http://.../tmp_imgs/doc_xxxx.pdf"}
```

最终文件输出到 `tmp_imgs/`，前端展示下载链接。

---

## 文件存储

| 目录 | 内容 | Git 跟踪 |
|------|------|----------|
| `doc_workspace/` | 中间 YAML 大纲（`outline_*.yaml`）和 Markdown 草稿（`draft_*.md`） | ❌（gitignore） |
| `tmp_imgs/` | 最终输出的 `.md` / `.docx` / `.pdf` | ❌（gitignore） |

`doc_workspace/.gitkeep` 保留在 git 中以确保目录存在。

---

## 前端组件

| 组件 | 路径 | 说明 |
|------|------|------|
| `YamlOutlineModal.vue` | `vue-front/src/components/YamlOutlineModal.vue` | 三步流程的整体 UI：YAML 编辑 → Markdown 预览/编辑 → 下载链接 |
| `RightPanel.vue` | `vue-front/src/components/RightPanel.vue` | 提供三个按钮入口 |
| `useChat.js` | `vue-front/src/composables/useChat.js` | `generateDocument()`、`generateDocumentUnified()`、`fetchGeneratedFilesForSession()` |

---

## 后端核心文件

| 文件 | 说明 |
|------|------|
| `agent/document_generator.py` | 所有文档生成逻辑：三种模式的 prompt、SSE 流、md/docx/pdf 转换 |
| `data_access/report_log.py` | 文档生成日志记录（`report_generation_log` 表） |