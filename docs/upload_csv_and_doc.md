# CSV 上传、导出与文档导入注释

## 1. 数据 CSV 导入 (`POST /upload-csv/`)

### 功能

上传 CSV 文件，自动创建 MySQL 表并插入数据。若表名已存在则先删除重建。

### 接口

| 项目 | 说明 |
|------|------|
| **URL** | `POST /upload-csv/` |
| **请求格式** | `multipart/form-data` |
| **字段** | `file`（CSV 文件，必填），`table_name`（表名，可选，默认 `uploaded_data`） |

### 数据类型推断

pandas 读取 CSV 后逐列推断：

| pandas dtype | MySQL 类型 | 判断依据 |
|---|---|---|
| `int64` | `Integer` | pandas 自动推断 |
| `float64` | `Float` | pandas 自动推断 |
| `datetime64` | `DateTime` | pandas 自动推断 |
| `bool` | `Boolean` | pandas 自动推断 |
| `object`（字符串） | `VARCHAR(n)` 或 `Text` | 非空值最大字符长度 ≤ 500 → `VARCHAR(长度×2，上限8000)`，否则 `Text` |
| 全空列 | `VARCHAR(255)` | 无数据时回退 |

### 名称清洗

自动处理非法标识符：

| 场景 | 处理方式 | 示例 |
|------|----------|------|
| 含非法字符（空格、符号等） | 替换为 `_` | `"user id"` → `user_id` |
| 数字开头 | 加前缀 | `"123abc"` → `col_123abc` 或 `tbl_123abc` |
| MySQL 保留字 | 末尾追加 `_` | `"select"` → `select_` |
| 空名称 | 回退默认值 | 表名 → `uploaded_data`，列名 → `column` |
| 名称冲突 | 末尾追加 `_` | 已有 `col_` → `col__` |

### 原子性与报错逻辑

1. **预校验阶段**（`_validate_rows`）— 逐行逐列检查类型兼容性，不接触数据库：
   - Integer → 尝试 `int(val)`
   - Float → 尝试 `float(val)`
   - DateTime → 尝试 `pd.to_datetime(val)`
   - Boolean → 检查值是否在 `true/false/1/0/yes/no` 中
   - VARCHAR → 检查字符串长度是否超过 `max_length`
   - 校验失败返回格式：`{success: false, error: "Validation failed:\nRow {line_no}, column '{col_name}': 具体原因"}`
2. **执行阶段** — 校验通过后创建表 + `df.to_sql()` 批量插入，全部在一个事务中（原子性）
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
| **字段** | `file`（文档文件），`table_name`（目标表名，默认 `uploaded_data`） |

### 处理流程

```
上传文档 → 提取文本 → LLM 分析 → 生成 ALTER TABLE 注释 SQL → 执行写入
```

1. **`process_file_content()`** — 按类型解析文本：
   - `.txt`：UTF-8 解码
   - `.docx`：python-docx 逐段落提取
   - `.pdf`：PyPDF2 逐页提取
   - `.doc`：尝试 UTF-8 解码（旧版二进制格式**不支持**）
2. **`get_llm_data_comment()`** — 提取文本 + 目标表结构 → LLM 生成 ALTER TABLE SQL
3. **`execute_sql_3()`** — 逐条执行生成的 SQL

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

## 7. 相关代码文件

| 文件 | 职责 |
|------|------|
| `main.py` | 所有接口路由定义 |
| `data_access/insert_data_from_csv.py` | CSV 解析、类型推断、名称清洗、预校验、建表写入 |
| `utils/process_file.py` | 文档格式解析（.txt / .docx / .pdf / .doc） |
| `agent/data_comment.py` | LLM 调用生成注释 SQL |
| `agent/tools/copilot/utils/read_db.py` | SQL 执行器（`execute_sql_3`） |
| `agent/tools/copilot/sql_code.py` | 数据库结构信息获取 |
| `vue-front/src/pages/DataUploadPage.vue` | 数据上传页 |
| `vue-front/src/pages/CommentManagePage.vue` | 注释管理页 |
| `vue-front/src/components/DbOverview.vue` | 数据库概览组件（含数据导出） |