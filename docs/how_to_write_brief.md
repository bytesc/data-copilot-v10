# Brief 编写指南

## 概述

Brief 是注入 LLM prompt 的概览性知识，帮助 LLM 理解数据库、业务领域、MCP 服务器和可用函数的能力范围。系统支持 5 种 Brief：多数可通过 **MD 文件**（静态）和 **`brief_info` 表**（动态）两种来源配置，两者合并后注入；FUNCTION_BRIEF 则完全硬编码在代码中。

---

## Brief 一览

| Brief | MD 文件 | `brief_info` attr | 注入阶段 | 标签 |
|-------|---------|-------------------|----------|------|
| DB_BRIEF | `agent/tools/base_knowledge/knowledge_docs/db_brief.md` | `db_brief` | think + action / explore_schema | `DataBase Brief` |
| BASE_KNOWLEDGE_BRIEF | `agent/tools/base_knowledge/knowledge_docs/base_knowledge_brief.md` | `base_knowledge_brief` | think + action / explore_base_knowledge | `Domain Knowledge Brief` |
| MCP_BRIEF | `agent/tools/base_knowledge/knowledge_docs/mcp_brief.md` | `mcp_brief` | think + action / explore_mcp | `MCP Brief` |
| FUNCTION_BRIEF | 代码硬编码 | 无 | think + action | `Function Brief` |
| CUSTOM_FUNC_BRIEF | `agent/tools/base_knowledge/knowledge_docs/custom_func_brief.md` | `custom_func_brief` | think + action / explore_functions | `Custom Function Brief` |

> 注：五种 Brief 全部通过 `BRIEF_INFO` 同时注入 think 与 action 两个阶段（`agent/think.py`、`agent/action.py`）；表中 "explore_*" 表示还会额外注入对应 act 提示词。其中 BASE_KNOWLEDGE_BRIEF / CUSTOM_FUNC_BRIEF 注入各自 act 提示词时**不带** `Domain Knowledge Brief` / `Custom Function Brief` 标签——这两个标签只存在于 `BRIEF_INFO` 的渲染中（DB_BRIEF / MCP_BRIEF 自带 `DataBase Brief:` / `MCP Brief:` 标签，随注入位置始终显示）。
>
> 另注：`knowledge_docs/` 下的 MD 文件（含表中列出的三个 brief 文件，以及 `base_knowledge.md`、`target_knowledge.md`、`db_query_guide.md`、`doc_guide.md`、`think_guide.md`）当前均为 0 字节空占位文件；Brief 实际内容来自 `brief_info` 表的对应行，MD 文件只是可选的合并来源（`_read_doc()` 对空/缺失文件返回空串，`_get_brief_value()` 把 `brief_info` 的值追加到 MD 内容之后）。

---

## MD 文件与 DB 的关系

### 合并机制

MD 文件和 `brief_info` 表的内容**不是二选一，而是合并**

### 生命周期差异

| 来源 | 加载时机 | 更新方式 |
|------|----------|----------|
| MD 文件 | 应用启动时（`_read_doc()` 一次读取并缓存） | 修改文件后需重启应用 |
| `brief_info` 表 | 每次使用 Brief 时实时查询 | 修改 DB 后立即生效，无需重启 |

### brief_info 表结构

```sql
-- sys 数据库
CREATE TABLE brief_info (
    attr  TEXT      NOT NULL,  -- 属性名称：db_brief / base_knowledge_brief / mcp_brief / custom_func_brief
    value LONGTEXT            -- 属性值：追加到对应 MD 文件后的文本内容
);
```

### 典型使用场景

- **MD 文件**：存放通用、稳定的 Brief 内容，随代码版本管理。
- **`brief_info` 表**：存放环境特定或需要频繁更新的补充内容（如客户定制信息），无需重启即可生效。

---

## 各 Brief 的用途

### DB_BRIEF — 数据库概览

**注入位置**：think + action 阶段（`BRIEF_INFO`）+ `explore_schema` act 提示词。

**作用**：说明数据库的整体领域和它能回答哪些类型的问题。

- 数据库是什么领域？覆盖了多少实体和关系？
- 能回答哪些典型问题（查询、分析路径）？

> ⚠️ 当系统切换连接了新数据库后，**必须更新**此 Brief，否则 LLM 会沿用旧数据库的描述。

### BASE_KNOWLEDGE_BRIEF — 基础业务知识摘要

**注入位置**：think + action 阶段（`BRIEF_INFO`，带 `Domain Knowledge Brief` 标签）+ `explore_base_knowledge` act 提示词（不带该标签）。

**作用**：说明业务领域的范围和能分析哪些业务问题。

- 业务领域范围和边界
- 能回答哪些业务问题

### MCP_BRIEF — MCP 服务器摘要

**注入位置**：think + action 阶段（`BRIEF_INFO`，带 `MCP Brief` 标签）+ `explore_mcp` act 提示词。

**作用**：说明有哪些 MCP 外部工具服务器可用、每个服务器提供什么能力。

- MCP 服务器列表及简要功能描述

> 新增 MCP 服务器时，除了配置 `config/mcp_servers.yaml`，还需在此 Brief 中添加服务器描述。

### FUNCTION_BRIEF — 函数摘要

**注入位置**：think + action 阶段（`BRIEF_INFO` 的 `Function Brief` 区段）。

**作用**：说明有哪些类别的函数可用。

- 内容完全硬编码在代码中，不依赖 MD 文件或数据库
- 函数的大类划分（仅数据库查询 Database 与可视化 Visualization 两大类）
- 每个大类能解决什么类型的问题

### CUSTOM_FUNC_BRIEF — 自定义函数摘要

**注入位置**：think + action 阶段（`BRIEF_INFO`，带 `Custom Function Brief` 标签）+ `explore_functions` act 提示词（不带该标签）。

**作用**：说明自定义/额外注册的函数的能力。

- 内容来自 MD 文件 `custom_func_brief.md` + `brief_info` 表的 `custom_func_brief` 行
- 用于描述用户自定义的函数（如 HDB 预测、地图、学校查询等）

---

## 如何编写 Brief

### 通用原则

1. **简洁准确**：Brief 是概览，不是手册。每个 Brief 控制在 10-20 行以内。
2. **突出能力**：用 "What it can do" 的视角组织内容，让 LLM 知道能回答什么问题。
3. **提供关键数字**：实体数、表数、关系数等量化信息让 LLM 评估范围。
4. **纯描述性**：不要写指令式内容（如"你必须使用某表"），指令应放在 action prompt 中。
5. **不使用 `#` 标题**：Brief 文件本身是纯文本描述，直接以 `DataBase:`、`Knowledge Base:` 等标签开头，不要使用 Markdown `#` 标题语法。
6. **不包含连接信息**：不要写入数据库连接地址、MCP 服务器 URL/端口、API key、用户名密码等基础设施和敏感信息。
7. **Markdown 格式**：文件内容会被包裹在 ` ```markdown ` 代码块中注入。

### db_brief.md 写法

格式参考 `agent/tools/base_knowledge/knowledge_docs/db_brief.md`（当前为空占位文件，以下为推荐格式）：

```markdown
DataBase:
一句话描述数据库的领域和规模。

What it can do:
- **能力一**：详细说明
- **能力二**：详细说明
- **能力三**：详细说明

关键指标：实体数、关系数等。
```

要点：
- 首行以 `DataBase:` 开头
- 第二行概括数据库领域和规模（实体数、关系数）
- `What it can do` 下列出 3-6 个典型查询/分析场景
- 末尾补充关键指标

### base_knowledge_brief.md 写法

格式参考 `agent/tools/base_knowledge/knowledge_docs/base_knowledge_brief.md`（当前为空占位文件，以下为推荐格式）：

```markdown
Knowledge Base:
一句话描述业务领域范围。

What it can do:
- **能力一**：详细说明
- **能力二**：详细说明

关键指标：可推荐的实体数、主要类型分布。
```

要点：
- 首行以 `Knowledge Base:` 开头
- 明确业务领域的边界（哪些问题能回答、哪些不能）
- `What it can do` 聚焦业务分析能力，而非数据查询能力
- 末尾注明关键指标

### mcp_brief.md 写法

格式参考 `agent/tools/base_knowledge/knowledge_docs/mcp_brief.md`（当前为空占位文件，以下为推荐格式）：

```markdown
MCP Servers:
一句话说明 MCP 是什么。

Server List:
- **server_name**：工具功能描述
- **server_name**：工具功能描述
```

要点：
- 首行以 `MCP Servers:` 开头
- `Server List` 下列出每个服务器名称和简要功能
- 新增 MCP 服务器时必须同步更新

### custom_func_brief.md 写法

格式参考 `agent/tools/base_knowledge/knowledge_docs/custom_func_brief.md`（当前为空占位文件，以下为推荐格式）：

```markdown
Custom Functions:
一句话说明系统提供了哪些自定义函数。

HDB 分析类：
- HDB 房价预测、价格趋势分析
- HDB 详细信息查询

地理信息类：
- 地图可视化，学校/幼儿园位置查询
```

要点：
- 首行以 `Custom Functions:` 开头
- 按**大类**组织，每类描述能解决什么问题
- **不要**列具体函数名和参数


## 相关文档

| 文档 | 说明 |
|------|------|
| `docs/how_to_modify_db_and_knowledge.md` | 知识配置项完整说明 |
| `docs/prompt_injection.md` | 动态提示词注入机制详解 |
| `docs/how_to_add_action.md` | 新增 Action（含 MCP Brief 更新说明） |