# CSV 上传与文档导入注释功能

## 1. CSV 上传 (`/upload-csv/`)

### 功能概述

上传 CSV 文件，自动创建 MySQL 表并插入数据。如果表名已存在则先删除重建。

### 接口

| 项目 | 说明 |
|------|------|
| **URL** | `POST /upload-csv/` |
| **请求格式** | `multipart/form-data` |
| **字段** | `file`（CSV 文件，必填），`table_name`（表名，可选，默认 `uploaded_data`） |

### 数据类型推断逻辑

pandas 读取 CSV 后逐列推断，映射关系：

| pandas dtype | MySQL 类型 | 判断依据 |
|---|---|---|
| `int64` | `Integer` | pandas 自动推断 |
| `float64` | `Float` | pandas 自动推断 |
| `datetime64` | `DateTime` | pandas 自动推断 |
| `bool` | `Boolean` | pandas 自动推断 |
| `object`（字符串） | `VARCHAR(n)` 或 `Text` | 非空值最大字符长度 ≤ 500 → `VARCHAR(长度×2，上限8000)`，否则 `Text` |
| 全空列 | `VARCHAR(255)` | 无数据可推断时回退 |

### 非法标识符处理

上传时自动清洗表名和列名，无需手动处理：

| 场景 | 处理方式 | 示例 |
|------|----------|------|
| 含非法字符（空格、符号等） | 替换为 `_` | `"user id"` → `user_id` |
| 数字开头 | 加前缀 | `"123abc"` → `col_123abc` 或 `tbl_123abc` |
| MySQL 保留字 | 末尾追加 `_` | `"select"` → `select_` |
| 空名称 | 回退 | 表名 → `uploaded_data`，列名 → `column` |
| 名称冲突 | 末尾追加 `_` | 已有 `col_` → `col__` |

### 前端界面

`DataPage.vue` → 选择 "CSV File" 标签 → 选择文件 → 可选填表名 → 点击 Upload。

### 返回示例

```json
{
  "type": "success",
  "message": "Successfully created table 'sales_data' and inserted 1500 records.",
  "row_count": 1500,
  "table_name": "sales_data"
}
```

---

## 2. 文档导入注释 (`/upload-txt/`)

### 功能概述

上传 .txt / .docx / .doc / .pdf 文档，系统通过 LLM 提取文档内容，自动为指定表生成表和列注释并写入数据库。

### 接口

| 项目 | 说明 |
|------|------|
| **URL** | `POST /upload-txt/` |
| **请求格式** | `multipart/form-data` |
| **字段** | `file`（文档文件），`table_name`（要注释的目标表名，默认 `uploaded_data`） |

### 处理流程

```
上传文档 → 提取文本 → LLM 分析 → 生成 ALTER TABLE 注释 SQL → 执行写入
```

1. **`process_file_content()`** — 按文件类型解析文本：
   - `.txt`：直接 UTF-8 解码
   - `.docx`：python-docx 逐段落提取
   - `.pdf`：PyPDF2 逐页提取
   - `.doc`：尝试 UTF-8 解码（旧版 .doc 二进制格式**不支持**）
2. **`get_llm_data_comment()`** — 将提取文本 + 目标表结构发送给 LLM，生成 ALTER TABLE 语句：
   - `ALTER TABLE \`表名\` COMMENT = '...'`（表注释）
   - `ALTER TABLE \`表名\` MODIFY COLUMN \`列名\` 类型 COMMENT '...'`（列注释）
3. **`execute_sql_3()`** — 逐条执行生成的 SQL

### 前置条件

- 目标表**必须已存在于数据库中**
- 依赖 LLM 调用，需确保 LLM 可用
- 依赖 `python-docx`（.docx）和 `PyPDF2`（.pdf）库

### 前端界面

`DataPage.vue` → 选择 "Document File" 标签 → 选择 .txt/.docx/.doc/.pdf → 输入表名 → 点击 Upload。

### 返回示例

```json
{
  "status": "success",
  "table_name": "sales_data",
  "extracted_text_length": 2350,
  "preview": "文档前500字...（截断）..."
}
```

---

## 3. 相关代码文件

| 文件 | 职责 |
|------|------|
| `main.py` | 接口路由定义（`/upload-csv/` 和 `/upload-txt/`） |
| `data_access/insert_data_from_csv.py` | CSV 解析、类型推断、清洗、建表写入 |
| `utils/process_file.py` | 文档格式解析（.txt / .docx / .pdf / .doc） |
| `agent/data_comment.py` | LLM 调用来生成注释 SQL |
| `agent/tools/copilot/utils/read_db.py` | SQL 执行器（`execute_sql_3`） |
| `agent/tools/copilot/sql_code.py` | 数据库结构信息获取（`get_db_info_prompt`） |
| `vue-front/src/pages/DataPage.vue` | 前端上传页面 |

## 4. 注意事项

- **CSV 列类型**依赖 pandas 自动推断，数字型字符串 ID 可能被误判为 `Integer`，建议上传前确认。
- **.doc 格式**（非 .docx）不被支持，请使用 .docx / .txt / .pdf。
- **文档注释生成**依赖 LLM 分析质量，生成的 SQL 可能不准确，建议上传后通过 "Comments" 页面审核并手动修正。
- 如果上传 CSV 时指定了已存在的表名，原表会被直接 **DROP** 后重建。
- `data_comment.py:27` 释放单引号转义逻辑：注释中的 `'` 自动转为 `''` 避免 SQL 语法错误。