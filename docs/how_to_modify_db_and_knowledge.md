# 接入新数据库的配置指南

## 1. 修改数据库连接

`config/config.yaml` 中的 `mysql` 字段改为新数据库的连接地址，`mysql_sys` 通常无需修改。

## 2. 表注释与字段注释

直接在 MySQL 中为表、字段添加 `COMMENT`，系统自动读取，无需额外配置。

## 3. 知识配置项

以下每个配置项均支持通过 **静态 MD 文件** 和/或 **数据库表** 配置，两者内容合并后一起注入提示词（并非二选一）。

### 3.1 DB_BRIEF — 数据库概览

| 来源 | 路径/表 |
|---|---|
| MD 文件 | `agent/tools/base_knowledge/knowledge_docs/db_brief.md` |
| 数据库表 | `brief_info` 中 `attr='db_brief'` 的行 |

两者合并后以 `DataBase Brief` 标签注入。

### 3.2 BASE — 基础业务知识

| 来源 | 路径/表 |
|---|---|
| MD 文件 | `agent/tools/base_knowledge/knowledge_docs/base_knowledge.md` |
| 数据库表 | `base_knowledge` 表（key-value 结构） |

两者合并后以 `base knowledge for reference` 标签注入。

### 3.3 DB_QUERY_GUIDE — SQL 查询指南

| 来源 | 路径/表 |
|---|---|
| MD 文件 | `agent/tools/base_knowledge/knowledge_docs/db_query_guide.md` |
| 数据库表 | `db_query_guide` 表（key-value 结构，每条记录一条指南） |

两者合并后以 `SQL Query guide` 标签注入。DB 中的每条记录会附加 `[id=N]` 标记。

### 3.4 DOC — 文档知识

| 来源 | 路径/表 |
|---|---|
| MD 文件 | `agent/tools/base_knowledge/knowledge_docs/doc_knowledge.md` |
| 数据库表 | `doc_knowledge` 表（key-value 结构） |

两者合并后以 `doc reference` 标签注入。

### 3.5 TARGET — 目标输出模板

| 来源 | 路径/表 |
|---|---|
| MD 文件 | `agent/tools/base_knowledge/knowledge_docs/target_knowledge.md` |
| 数据库表 | 无 |

仅支持 MD 文件，以 `Target` 标签注入。

### 3.6 THINK_KNOWLEDGE — 思考分析策略

| 来源 | 路径/表 |
|---|---|
| MD 文件 | 无 |
| 数据库表 | `think_knowledge` 表（key-value 结构） |

仅支持数据库表，以 `think knowledge for reference` 标签注入。

### 3.7 BRIEF_INFO — 摘要信息

| 条目 | MD 文件 | 数据库表 |
|---|---|---|
| 数据库概览 | `knowledge_docs/db_brief.md` | `brief_info` 中 `attr='db_brief'` |
| 知识摘要 | `knowledge_docs/base_knowledge_brief.md` | `brief_info` 中 `attr='base_knowledge_brief'` |

两者合并后注入。

## 4. 汇总

| 配置项 | MD 文件 | DB 表 | 关系 |
|---|---|---|---|
| DB_BRIEF | `db_brief.md` | `brief_info.db_brief` | 合并 |
| BASE | `base_knowledge.md` | `base_knowledge` | 合并 |
| DB_QUERY_GUIDE | `db_query_guide.md` | `db_query_guide` | 合并 |
| DOC | `doc_knowledge.md` | `doc_knowledge` | 合并 |
| TARGET | `target_knowledge.md` | 无 | 仅 MD |
| THINK_KNOWLEDGE | 无 | `think_knowledge` | 仅 DB |
| BRIEF_INFO.db_brief | `db_brief.md` | `brief_info` 中 `attr='db_brief'` | 合并 |
| BRIEF_INFO.base_knowledge_brief | `base_knowledge_brief.md` | `brief_info` 中 `attr='base_knowledge_brief'` | 合并 |

## 5. 验证

启动后访问 `GET /api/db-overview/` 查看是否正确读取了表和字段注释。