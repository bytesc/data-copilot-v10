# 接入新数据库的配置指南

## 1. 修改数据库连接

`config/config.yaml` 中的 `mysql` 字段改为新数据库的连接地址，`mysql_sys` 通常无需修改。

## 2. 表注释与字段注释

直接在 MySQL 中为表、字段添加 `COMMENT`，系统自动读取，无需额外配置。

## 3. 知识配置项

以下每个配置项均支持通过 **静态 MD 文件** 和/或 **数据库表** 配置，两者内容合并后一起注入提示词（并非二选一）。

### 3.1 DB_BRIEF / DB_BRIEF_BRIEF — 数据库概览

| 来源 | 路径/表 |
|---|---|
| MD 文件 | `agent/tools/base_knowledge/knowledge_docs/db_brief.md` |
| 数据库表 | `brief_info` 中 `attr='db_brief'` 的行 |

- `DB_BRIEF`：用于 `explore_schema` action，带 `DataBase Brief` 标签
- `DB_BRIEF_BRIEF`：用于 think 阶段的 `## Database Brief` 区段（纯内容，无额外前缀）

### 3.2 BASE_KNOWLEDGE_BRIEF — 基础业务知识摘要

| 来源 | 路径/表 |
|---|---|
| MD 文件 | `agent/tools/base_knowledge/knowledge_docs/base_knowledge_brief.md` |
| 数据库表 | `brief_info` 中 `attr='base_knowledge_brief'` 的行 |

用于 think 阶段的 `## Domain Knowledge Brief` 区段。**仅摘要**，完整业务知识（`base_knowledge` 表）通过 `explore_base_knowledge` action 按需获取。

### 3.3 DB_QUERY_GUIDE — SQL 查询指南

| 来源 | 路径/表 |
|---|---|
| MD 文件 | `agent/tools/base_knowledge/knowledge_docs/db_query_guide.md` |
| 数据库表 | `db_query_guide` 表（key-value 结构，每条记录一条指南） |

两者合并后以 `SQL Query guide` 标签注入。DB 中的每条记录会附加 `[id=N]` 标记。仅用于 `explore_schema` action。

### 3.4 Function Brief — 函数摘要

| 来源 | 说明 |
|---|---|
| 代码自动生成 | `get_func_summary_for_agent()` |

用于 think 阶段的 `## Function Brief` 区段。自动从注册的函数列表中生成摘要表格（函数名、分类、用途）。

### 3.5 MCP_BRIEF — MCP 服务器摘要

| 来源 | 路径/表 |
|---|---|
| MD 文件 | `agent/tools/base_knowledge/knowledge_docs/mcp_brief.md` |
| 数据库表 | `brief_info` 中 `attr='mcp_brief'` 的行 |

用于 think 阶段的 `## MCP Brief` 区段和 `explore_mcp` action。

### 3.6 TARGET — 目标输出模板

| 来源 | 路径/表 |
|---|---|
| MD 文件 | `agent/tools/base_knowledge/knowledge_docs/target_knowledge.md` |
| 数据库表 | 无 |

仅支持 MD 文件，仅用于 think 阶段。需非空时才会注入。

### 3.7 BASE — 基础业务知识（完整）

| 来源 | 路径/表 |
|---|---|
| MD 文件 | `agent/tools/base_knowledge/knowledge_docs/base_knowledge.md` |
| 数据库表 | `base_knowledge` 表（key-value 结构） |

**不再注入 think / action 提示词**。仅通过 `explore_base_knowledge` action 按需获取。`BASE_KNOWLEDGE_BRIEF` 为其摘要版本。

### 3.8 DOC — 文档知识

| 来源 | 路径/表 |
|---|---|
| MD 文件 | `agent/tools/base_knowledge/knowledge_docs/doc_knowledge.md` |
| 数据库表 | `doc_knowledge` 表（key-value 结构） |

仅通过 `explore_base_knowledge` action 按需获取。

### 3.9 THINK_KNOWLEDGE — 思考分析策略

| 来源 | 路径/表 |
|---|---|
| MD 文件 | `agent/tools/base_knowledge/knowledge_docs/think_knowledge.md` |
| 数据库表 | `think_knowledge` 表（key-value 结构） |

仅通过 `explore_base_knowledge` action 按需获取。

## 4. 汇总

| 配置项 | MD 文件 | DB 表 | 使用阶段 | 关系 |
|---|---|---|---|---|---|
| DB_BRIEF | `db_brief.md` | `brief_info.db_brief` | explore_schema | 合并 |
| DB_BRIEF_BRIEF | `db_brief.md` | `brief_info.db_brief` | think | 合并 |
| BASE_KNOWLEDGE_BRIEF | `base_knowledge_brief.md` | `brief_info.base_knowledge_brief` | think | 合并 |
| MCP_BRIEF | `mcp_brief.md` | `brief_info.mcp_brief` | think / explore_mcp | 合并 |
| Function Brief | 代码自动生成 | 无 | think | 自动 |
| BASE | `base_knowledge.md` | `base_knowledge` | explore_base_knowledge | 合并（按需获取） |
| DOC | `doc_knowledge.md` | `doc_knowledge` | explore_base_knowledge | 合并（按需获取） |
| THINK_KNOWLEDGE | `think_knowledge.md` | `think_knowledge` | explore_base_knowledge | 合并（按需获取） |
| DB_QUERY_GUIDE | `db_query_guide.md` | `db_query_guide` | explore_schema | 合并 |
| TARGET | `target_knowledge.md` | 无 | think | 仅 MD |

## 5. 验证

启动后访问 `GET /api/db-overview/` 查看是否正确读取了表和字段注释。