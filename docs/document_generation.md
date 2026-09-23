# 文档生成系统

三种模式，输出 `.md` / `.docx` / `.pdf`。

---

## 模式对比

| | Generate Report (📄) | Generate Document (📋) | YAML Outline (📐) |
|---|---|---|---|---|
| 按钮 | RightPanel | RightPanel | RightPanel |
| 后端 | `POST /api/generate-document/stream/` | `POST /api/generate-document/stream/unified/` | 三步：① outline ② from-yaml ③ finalize |
| LLM | 2轮：大纲JSON → 逐节 | 1轮：整篇 | 2轮：YAML → 逐节 |
| 人工干预 | 无 | 无 | ✅ 编辑YAML（代码/可视化双模式）+ 逐节确认 |
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

### 2. 恢复（Continue 按钮触发）

```
GET /api/doc-workspace/file/outline_{session_id}_{base}.yaml
```
前端从文件名提取 `base_full = {session_id}_{base}`，按优先级恢复：
1. `GET /api/doc-workspace/file/draft_{base_full}.md` → **200** → 解析章节，跳转 **review**
2. 无合并稿，逐文件请求 `GET /api/doc-workspace/file/draft_{base_full}_sNN.md` → **有文件** → 恢复已确认节（最后一节不加入 confirmedSections，放入编辑缓冲区避免重复），跳转 **sections**
3. 都 **404** → 跳转 **YAML 编辑**

### 3. 生成 YAML 大纲

```
POST /api/generate-document/generate-yaml-outline/
Body: { conversation_history, session_id }
```
SSE: `yaml_outline: msg → chunk×N → done { content, yaml_base, yaml_file }`

**YAML 格式定义**:
```yaml
title: "文档标题"                      # 最终 .docx/.pdf 居中显示
sections:
  - heading: "1. 章节标题"
    description: "章节描述（1-2句）"
    elements:                          # 可选，按顺序列出每个内容块
      - type: text                     # text / table / image
        description: "简述本段文字内容"
      - type: table
        description: "简述表格内容"
      - type: image
        description: "简述图表内容"
    subsections:
      - heading: "1.1 子节标题"
        description: "子节描述"
        elements:                      # 子节也可有 elements
          - type: text
            description: "简述"
          - type: image
            description: "简述"
```

- `elements` 为可选字段，每个元素有 `type`（`text`/`table`/`image`）和简短 `description`。
- `YAML_PART_SYSTEM` 规则 10 要求 LLM 按照 `elements` 定义的顺序和类型生成内容。

### 3b. 双模式编辑器

YAML 编辑步骤（Step 1）提供 **Code**（代码）和 **Visual**（可视化）两种编辑模式，顶部标签切换：

| 模式 | 说明 |
|------|------|
| **Code** | 纯文本 textarea，直接编辑 YAML 源码（原有方式） |
| **Visual** | 表单界面：标题输入框、章节卡片（含 heading/description/elements/subsections），支持添加/删除/排序 |

- 切换至 Visual 模式时自动校验 YAML 合法性，非法 YAML 会提示错误并停留在 Code 模式
- 两种模式共享同一份数据，切换时自动同步
- 使用 `js-yaml` 库在前端完成解析和序列化

### 4. 逐节生成

```
POST /api/generate-document/stream/from-yaml/
Body: { conversation_history, yaml_outline, session_id, yaml_base, section_index, confirmed_sections }
```
SSE: `msg → section_msg → chunk×N → section_done`

> `YAML_PART_SYSTEM` 规则 1 强制 LLM 不输出 `##` 标题（后端自动追加）。

### 5. 最终输出

```
POST /api/generate-document/finalize/
Body: { markdown_content, session_id, yaml_base, conversation_history }
```
SSE: `finalize: done { download_url_md/docx/pdf }`

保存到 `tmp_imgs/`，**自动清理** `doc_workspace/` 中对应文件。

---

## 弹窗 UI 交互

| 步骤 | 关键交互 | 底部按钮 |
|------|----------|----------|
| pick | 文件列表：Ask AI / Continue / Edit / View / ✕ | Cancel |
| yaml | 顶部 **Code / Visual** 标签切换编辑模式；Visual 模式以表单形式编辑标题、章节、元素和子节 | Back \| Save \| Generate Sections |
| sections | 流式预览已确认节 + 当前节编辑框 | Confirm & Next / Confirm & Finish |
| review | 点击 `Section N` 徽标可跳回编辑任意节 | Back \| Save Draft \| Finalize to docx/pdf |
| 所有步骤 | 右上角 ✕ 关闭 + 点击遮罩层关闭 | — |

### Ask AI

调用 `POST /api/generate-document/yaml-to-prompt/`，后端用英文指令 + YAML 组合 prompt，前端通过 `submitNewQuestion()` 发给主 LLM（仅收集信息，不生成文档）。

### 自定义弹窗确认

- **删除** → `DELETE /api/doc-workspace/outline/{filename}`（仅删 outline）
- **Edit** → `DELETE /api/doc-workspace/drafts/{session_id}/{yaml_id}`（删草稿，保留 outline）

### Save（不跳步骤）

- YAML: 保存 `outline_{yamlBase}.yaml`
- Review: 保存 `draft_{yamlBase}.md`
- 调用 `POST /api/doc-workspace/save/{filename}`

---

## 后端 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/doc-workspace/files/` | 列出 outline YAML |
| GET | `/api/doc-workspace/file/{filename}` | 读取文件 |
| POST | `/api/doc-workspace/save/{filename}` | 保存文件 |
| DELETE | `/api/doc-workspace/outline/{filename}` | 仅删 outline |
| DELETE | `/api/doc-workspace/drafts/{session_id}/{yaml_id}` | 按 session+yaml_id 删草稿 |
| POST | `/api/generate-document/generate-yaml-outline/` | 生成 YAML 大纲（SSE） |
| POST | `/api/generate-document/stream/from-yaml/` | 逐节生成（SSE） |
| POST | `/api/generate-document/finalize/` | 最终输出（SSE） |
| POST | `/api/generate-document/yaml-to-prompt/` | YAML → 指令 prompt |

---

## 文件存储

| 路径 | 内容 | 命名 |
|------|------|------|
| `doc_workspace/` | YAML 大纲 | `outline_{sid}_{rand8}.yaml` |
| `doc_workspace/` | 单节草稿 | `draft_{sid}_{base}_sNN.md` |
| `doc_workspace/` | 合并草稿 | `draft_{sid}_{base}.md` |
| `tmp_imgs/` | 最终文档 | `doc_{rand8}.md/.docx/.pdf` |

---

## 重复标题防护

| 模式 | 方式 |
|------|------|
| YAML Outline | 规则 1 + 尾部指令禁止 LLM 输出 `##` |
| Generate Report | prompt 尾部显式禁止重复 |
| Generate Document | 单轮自包含 |

---

## 组件 & 文件

| 文件 | 说明 |
|------|------|
| `vue-front/src/components/YamlOutlineModal.vue` | 主弹窗组件，含 Code/Visual 模式切换逻辑 |
| `vue-front/src/components/YamlVisualEditor.vue` | 可视化编辑表单组件（v-model 双向绑定 YAML 字符串） |
| `vue-front/src/composables/useChat.js` | `submitNewQuestion()` |
| `agent/document_generator.py` | 全部后端逻辑 |
| `data_access/report_log.py` | 文档日志 |