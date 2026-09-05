# 接入新数据库的配置指南

## 1. 修改数据库连接

`config/config.yaml` 中的 `mysql` 字段改为新数据库的连接地址，`mysql_sys` 通常无需修改。

## 2. 需要准备的内容

### 2.1 表注释与字段注释

直接在 MySQL 中为表、字段添加 `COMMENT`，系统自动读取，无需额外配置。

### 2.2 数据库概览

| 来源 | 说明 |
|---|---|
| 静态文件 `knowledge_docs/db_brief.md` | 数据库的整体业务描述 |
| 数据库表 `brief_info` 中 `attr='db_brief'` 的行 | 同上 |

**关系：** 两者合并后一起注入提示词，并非二选一。

### 2.3 基础知识摘要

| 来源 | 说明 |
|---|---|
| 静态文件 `knowledge_docs/base_knowledge_brief.md` | 业务重点摘要 |
| 数据库表 `brief_info` 中 `attr='base_knowledge_brief'` 的行 | 同上 |

**关系：** 两者合并后一起注入，并非二选一。

### 2.4 SQL 查询指南

| 来源 | 说明 |
|---|---|
| 静态文件 `knowledge_docs/db_query_guide.md` | 静态参考文档 |
| 数据库表 `db_query_guide` | 每条记录一条指南（key-value 结构） |

**关系：** 两者合并后一起注入，并非二选一。建议在 DB 中按 key-value 存储，方便动态增删。

### 2.5 基础业务知识

| 来源 | 说明 |
|---|---|
| 静态文件 `knowledge_docs/base_knowledge.md` | 通常为空，知识存储在 DB |
| 数据库表 `base_knowledge` | 每条记录一条知识（key-value 结构） |

**关系：** 两者合并后一起注入，并非二选一。建议在 DB 中存储。

## 3. 知识库表汇总（系统数据库 `data_copilot_v10_sys`）

| 表名 | 用途 | 接入新数据库时 |
|---|---|---|
| `brief_info` | 存储 `db_brief`（数据库概览）和 `base_knowledge_brief`（知识摘要） | **必须配置** |
| `db_query_guide` | SQL 查询指南，每条记录一条 | 推荐配置 |
| `base_knowledge` | 基础业务知识，每条记录一条 | 按需配置 |
| `doc_knowledge` | 文档知识 | 按需配置 |
| `code_guide` | 图表代码指南 | 按需配置 |
| `think_knowledge` | 思考分析策略 | 按需配置 |

## 4. 静态文件汇总（`agent/tools/base_knowledge/knowledge_docs/`）

| 文件 | 用途 | 接入新数据库时 |
|---|---|---|
| `db_brief.md` | 数据库概览 | 推荐编写 |
| `base_knowledge_brief.md` | 知识摘要 | 推荐编写 |
| `db_query_guide.md` | SQL 查询指南 | 可选（建议用 DB 表） |
| `base_knowledge.md` | 基础业务知识 | 可选（建议用 DB 表） |
| `doc_knowledge.md` | 文档知识 | 按需 |
| `target_knowledge.md` | 目标输出模板 | 按需 |

## 5. 验证

启动后访问 `GET /api/db-overview/` 查看是否正确读取了表和字段注释。