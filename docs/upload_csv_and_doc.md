# CSV 上传、导出与文档导入注释

> Multipart 接口无法使用 JSON 的 `{meta, data}` 信封。前端会在 `FormData` 中附加 `meta` 文本字段
> （JSON 字符串），目前只有 `POST /upload-txt/` 会读取并用于后续 LLM 调用；其余上传接口会忽略它。

## 上传大小限制

各上传接口对上传体积设有硬性上限，超限返回 `HTTP 413`（上限为 `main.py` 中的常量）：

| 接口 | 上限 | 常量 |
|------|------|------|
| `POST /upload-csv/` | 50 MB | `MAX_CSV_UPLOAD_BYTES` |
| `POST /upload-txt/` | 20 MB | `MAX_DOC_UPLOAD_BYTES` |
| `POST /api/comment-manage/{table_name}/import-csv` | 5 MB | `MAX_COMMENT_CSV_BYTES` |

- **入口预检**：中间件 `limit_multipart_upload_size` 在解析 `multipart/form-data` 前按 `Content-Length` 判断，
  超过三者最大值（50 MB，`MAX_MULTIPART_BYTES`）直接返回 `413`。
- **端点读取**：各处理函数通过 `_read_upload_limited(file, 上限)` 以 1 MiB 分块读取，累计超过该接口上限即 `413`。
  因此无 `Content-Length` 的分块传输也能按接口上限拦截，且不会把整包读入内存。
- `front.py` 反向代理**不设限**，仅透传请求；限制一律以后端为准。
- **编辑开关**：配置 `enable_edit: false` 时，涉及改库的接口一律返回 `403`（`main.py` 的 `_require_edit_enabled`），包括 `/upload-csv/`、`/upload-txt/`、数据/注释导出、注释导入与更新、`/api/db-overview/`、删除表；系统知识库路由同样受限。

## 1. 数据 CSV 导入 (`POST /upload-csv/`)

### 功能

上传 CSV 文件，自动创建 MySQL 表并插入数据。若表名已存在则先删除重建。

### 接口

| 项目 | 说明 |
|------|------|
| **URL** | `POST /upload-csv/` |
| **请求格式** | `multipart/form-data` |
| **字段** | `file`（CSV 文件，必填），`table_name`（表名，可选，默认 `uploaded_data`） |

> `file` 大小上限 **50 MB**，超限返回 `413`。


### 数据类型推断

pandas 读取 CSV 后逐列推断：

| pandas dtype | MySQL 类型 | 判断依据 |
|---|---|---|
| `int64` | `BigInteger` | pandas 自动推断（int64 范围超出 MySQL INT，避免大数值溢出报错） |
| `float64` | `Float` | pandas 自动推断 |
| `datetime64` | `DateTime` | pandas 自动推断 |
| `bool` | `Boolean` | pandas 自动推断 |
| `object`（字符串） | `VARCHAR(n)` 或 `Text` | 先取 `min(非空值最大字符长度×2, 8000)`，再判断 ≤ 500 → 仅当原始最大长度 ≤ 250 时用 `VARCHAR(长度×2)`，否则 `Text`（8000 上限实际不可达） |
| 全空列 | `VARCHAR(255)` | 无数据时回退 |

### 名称清洗

自动处理非法标识符：

| 场景 | 处理方式 | 示例 |
|------|----------|------|
| 含非法字符（空格、符号等） | 替换为 `_` | `"user id"` → `user_id` |
| 数字开头 | 加前缀 | `"123abc"` → `col_123abc` 或 `tbl_123abc` |
| 硬编码保留字 | 末尾追加 `_` | `"select"` → `select_`（仅覆盖代码内硬编码的约 59 个常见词，`interval`/`limit`/`offset`/`rank`/`value` 等不在其中） |
| 空名称 | 加前缀（后续回退分支不可达） | 空字符串清洗后为 `''`，随即进入加前缀分支变成 `col_`（列名）/`tbl_`（表名），因此 `if not cleaned` 的 `column`/`uploaded_data` 回退永不触发；表名默认值 `uploaded_data` 只来自接口 `Form` 默认值 |
| 名称冲突 | 末尾追加 `_` | 已有 `col_` → `col__` |

### 原子性与报错逻辑

1. **预校验阶段**（`_validate_rows`）— 逐行逐列检查类型兼容性，不接触数据库：
   - Integer → 尝试 `int(val)`
   - Float → 尝试 `float(val)`
   - DateTime → 尝试 `pd.to_datetime(val)`
   - Boolean → 检查值是否在 `true/false/1/0/yes/no` 中
   - VARCHAR → 检查字符串长度是否超过 `max_length`
   - 校验失败返回格式：`{success: false, error: "Validation failed:\nRow {line_no}, column '{col_name}': 具体原因"}`
   - 报错条数上限 100：超出后仅追加一行 `"... more validation errors omitted (N rows checked)"`，不再逐条列出
2. **执行阶段** — 校验通过后先创建表，再 `df.to_sql()` 批量插入，**分为两个独立操作，非事务性**。如果插入阶段失败，已创建的表不会自动回滚。
   - 执行失败返回格式：`{success: false, error: "Import failed. The DB reports: MySQL错误信息（含行列号）"}`
3. **成功返回**：
   ```json
   { "success": true, "message": "...", "row_count": 1500, "table_name": "sales_data" }
   ```

---

## 2. 数据 CSV 导出 (`GET /api/table/{table_name}/export-data-csv`)

### 功能

将指定表的**全部数据行**导出为 CSV 文件下载，服务器不留临时文件。

### 接口

| 项目 | 说明 |
|------|------|
| **URL** | `GET /api/table/{table_name}/export-data-csv` |
| **返回** | `Content-Disposition: attachment; filename="{table_name}_data.csv"` |
| **编码** | UTF-8 BOM，Excel 直接打开不乱码 |

### 前端

`DataUploadPage`（`DbOverview.vue`）— 每张表详情内 **Export Data** 按钮。

---

## 3. 注释 CSV 导出 (`GET /api/comment-manage/{table_name}/export-csv`)

### 功能

将指定表的**表注释 + 各列注释**导出为 CSV 文件下载，服务器不留临时文件。

### CSV 格式

```csv
column_name,comment
__table_comment__,这是用户表
id,主键ID
name,用户名
email,邮箱地址
```

- 首行 `__table_comment__` 表示表级注释
- 其余行对应各列注释
- 列头为 `column_name` 和 `comment`，可直接用于重新导入

### 前端

`CommentManagePage` — 每张表展开后的 **Export CSV** 按钮。

---

## 4. 注释 CSV 导入 (`POST /api/comment-manage/{table_name}/import-csv`)

### 功能

上传 CSV 批量导入/更新指定表的注释。CSV 格式与导出完全兼容。

### 接口

| 项目 | 说明 |
|------|------|
| **URL** | `POST /api/comment-manage/{table_name}/import-csv` |
| **请求格式** | `multipart/form-data` |
| **字段** | `file`（CSV 文件） |

> CSV 大小上限 **5 MB**，超限返回 `413`。


### CSV 要求

| 列头 | 说明 |
|------|------|
| `column_name` | 列名，或 `__table_comment__`（表示表级注释） |
| `comment` | 要设置的注释文本 |

### 原子性与报错逻辑

1. **验证阶段** — 逐行检查 `column_name` 是否为目标表的合法列名或 `__table_comment__`：
   - 发现未知列名立刻返回 `{success: false, error: "Validation failed:\nRow {line_no}: Unknown column '{col_name}'"}`
   - 不执行任何 ALTER TABLE
2. **执行阶段** — 验证通过后逐条执行 `ALTER TABLE` / `ALTER TABLE MODIFY COLUMN`：
   - 由于 MySQL DDL 自动提交，无法跨语句回滚
   - 普通情况下名称校验通过后 ALTER TABLE 不会失败
   - 异常返回格式：`{success: false, error: "Import failed. The DB reports: MySQL错误"}`
3. **成功返回**：
   ```json
   { "success": true, "table_comment_updated": true, "columns_updated": 5 }
   ```

---

## 5. 文档导入生成注释 (`POST /upload-txt/`)

### 功能

上传 .txt / .docx / .doc / .pdf 文档，LLM 提取内容后为指定表生成注释并写入数据库。

### 接口

| 项目 | 说明 |
|------|------|
| **URL** | `POST /upload-txt/` |
| **请求格式** | `multipart/form-data` |
| **字段** | `file`（文档文件），`table_name`（目标表名，默认 `uploaded_data`），`meta`（模型选择 JSON，可选） |

> `file` 大小上限 **20 MB**，超限返回 `413`。


### 处理流程

```
上传文档 → 提取文本 → LLM 分析生成注释 JSON → 服务端构建注释 DDL → 执行写入
```

1. **`process_file_content()`** — 按类型解析文本：
   - `.txt`：容错解码（依次尝试 `utf-8-sig` → `gb18030` → `latin-1`，最终回退 `errors="replace"`）
   - `.docx`：python-docx 逐段落提取
   - `.pdf`：PyPDF2 逐页提取（无可提取文本的扫描件返回 400）
   - `.doc`：按文件头识别真实格式——旧版二进制（OLE2）返回 400；ZIP 头（改名为 .doc 的 .docx）交给 .docx 解析器；RTF 走 `_strip_rtf` 提取；其余按 .txt 方式容错解码
2. **`get_llm_data_comment()`** — 提取文本 + 目标表结构 → LLM 仅返回 JSON `{"table_comment", "columns"}`（prompt 明确禁止输出任何 ALTER TABLE / DROP / DELETE / INSERT / UPDATE 语句）
3. **`_apply_table_comments()`** — 服务端从 `SHOW CREATE TABLE` 取原始列定义、仅替换 COMMENT 子句构建 DDL（`utils/column_ddl.py` 的 `build_table_comment_sql` / `build_column_comment_sql`），列名对照真实 schema 白名单过滤后经 `exec_driver_sql` 执行

### 响应

**成功 `200`**
```json
{
  "status": "success",
  "success": true,
  "message": "Comments were generated and applied to table 'uploaded_data'.",
  "table_name": "uploaded_data",
  "comment_applied": true,
  "extracted_text_length": 2500,
  "preview": "提取的内容前500字..."
}
```

> 接口会返回注释写入结果：若模型未返回有效注释 JSON 或注释未能写入目标表，仍返回 `200`，但 `success` 为 `false`、`status` 为 `"error"`，并在 `error` 字段给出原因。

**失败**: 无效/不可读的 `.docx`、不可读的 PDF、无文本层（扫描件）的 PDF、旧版二进制 `.doc` 等解析失败返回 `HTTP 400`；其余非 HTTP 异常才返回 `HTTP 500`，detail 为错误信息。

### 前置条件

- 目标表**必须已存在**
- 依赖 LLM 可用
- 依赖 `python-docx`（.docx）和 `PyPDF2`（.pdf）库

### 注意

生成的注释建议在 "Comments" 页面审核后手动修正。

---

## 6. 前端页面

| 页面 | 路由 | 功能 |
|------|------|------|
| `DataUploadPage`（含 `DbOverview`） | `/data` | 数据 CSV 上传/下载、文档上传 |
| `CommentManagePage` | `/data/comments` | 注释 CSV 导入/导出、逐条编辑 |

---

## 7. 用户上传图片（随 JSON 请求）

图片上传与 CSV/文档不同，**不使用 Multipart 接口**。前端选择图片后先在浏览器暂存，点击发送时才编码为 base64，放进 `conversation_history` 的 user 条目 `uploaded` 字段，随 Think/Action 等 JSON 请求提交；后端信封中间件解码保存为 `tmp_imgs/upload_<8位小写字母>.png`，把 `uploaded` 改写为文件名列表并追加进 blackboard 的 `selected_images`。

| 项目 | 说明 |
|------|------|
| 传输 | base64 data URL，位于 JSON 请求 `data.conversation_history[].uploaded`（`[{"name", "data"}]`） |
| 保存 | `tmp_imgs/upload_<8位小写字母>.png`（扩展名与生成图片一致，非 RGB/RGBA 会转换） |
| 落库 | `uploaded` 改写为文件名列表，并合并进 blackboard 的 `selected_images` 区域 |
| 张数 | 前端最多 10 张；后端每次请求同样最多处理 10 张（`MAX_IMAGES_PER_REQUEST`），且整包 base64 总量上限 50MB（`MAX_TOTAL_IMAGE_BYTES`），超限图片会被静默丢弃 |
| 单张大小 | ≤ 20MB，超限或解码/保存失败会被跳过 |
| 幂等 | `uploaded` 已是文件名字符串时不再处理、不重复合并 |
| 实现 | `utils/image_ingest.py` 的 `ingest_uploaded_images`（经 `main.py` 的 `unified_request_envelope` 调用） |

详见 `docs/api.md` 的「用户上传图片」与 `docs/conversation_history_structure.md` 的「用户输入 → 上传图片」。

---

## 8. 相关代码文件

| 文件 | 职责 |
|------|------|
| `main.py` | 所有接口路由定义；请求信封中间件 |
| `data_access/insert_data_from_csv.py` | CSV 解析、类型推断、名称清洗、预校验、建表写入 |
| `utils/process_file.py` | 文档格式解析（.txt / .docx / .pdf / .doc） |
| `utils/image_ingest.py` | 用户上传图片：base64 解码、保存为 upload_*.png、写入 history/blackboard |
| `agent/data_comment.py` | LLM 生成注释 JSON + 服务端构建/执行注释 DDL（本流程实现） |
| `utils/column_ddl.py` | 依据 `SHOW CREATE TABLE` 构建改注释 DDL（本流程实现） |
| `agent/tools/copilot/sql_code.py` | 数据库结构信息获取 |
| `vue-front/src/pages/DataUploadPage.vue` | 数据上传页 |
| `vue-front/src/pages/CommentManagePage.vue` | 注释管理页 |
| `vue-front/src/components/DbOverview.vue` | 数据库概览组件（含数据导出） |
| `vue-front/src/components/ChatArea.vue` | 聊天输入区（含图片选择/暂存/预览） |
| `vue-front/src/composables/useChat.js` | 会话流程（含发送时 base64 编码） |