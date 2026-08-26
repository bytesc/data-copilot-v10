# 动态提示词注入机制

## 概述

系统通过两类知识源向 LLM prompt 注入上下文：**MD 文件**（启动时加载，重启更新）和 **数据库表**（每次实时查询，无需重启）。注入点分布在 `Think → Action → Act → Observe` 的各个阶段。

---

## 知识源

### 1. MD 文件（启动时加载，重启更新）

存放在 `agent/tools/base_knowledge/knowledge_docs/`，模块导入时通过 `_read_doc()` 读取一次并缓存：

| 文件 | 缓存变量 |
|------|----------|
| `db_brief.md` | `_DB_BRIEF_MD` |
| `base_knowledge.md` | `_BASE_MD` |
| `doc_knowledge.md` | `_DOC_MD` |
| `target_knowledge.md` | `_TARGET_MD` |
| `db_query_guide.md` | `_DB_QUERY_GUIDE_MD`（当前未启用） |

### 2. 数据库表（实时查询，无需重启）

位于 `data_copilot_v10_sys` 数据库，每张表结构相同：

```sql
id    INT AUTO_INCREMENT PRIMARY KEY
key   TEXT NOT NULL
value LONGTEXT
```

| 表 | 查询函数 |
|----|----------|
| `base_knowledge` | `get_base_knowledge_db()` |
| `doc_knowledge` | `get_doc_knowledge_db()` |
| `db_query_guide` | `get_db_query_guide_db()`（当前未启用） |
| `code_guide` | `get_code_guide_db()` |
| `think_knowledge` | `get_think_knowledge_db()` |

### 3. 动态注入机制：`_DynamicStr`

`get_base_knowledge.py:275-289` 定义了一个代理类，使模块级变量在每次使用时重新计算，而非在导入时固定：

```python
class _DynamicStr:
    def __init__(self, func):       self.func = func
    def __str__(self):              return self.func()
    def __add__(self, other):       return str(self) + other
    def __radd__(self, other):      return other + str(self)
    def strip(self):                return str(self).strip()
    def __format__(self, spec):     return format(str(self), spec)
```

模块级变量将 MD 内容（启动时缓存）和 DB 内容（实时查询）拼接：

```python
BASE = _DynamicStr(lambda: "\nbase knowledge for reference:\n" + _BASE_MD
       + "\n" + base_knowledge_to_str(get_base_knowledge_db()))
DOC = _DynamicStr(lambda: "\ndoc reference(just for reference):\n" + _DOC_MD
       + "\n" + base_knowledge_to_str(get_doc_knowledge_db()))

THINK_KNOWLEDGE = _DynamicStr(lambda: "\nthink knowledge for reference:\n" + base_knowledge_to_str(get_think_knowledge_db()))
```

---

## 按功能划分的注入分析

### 1. Think 阶段 — 分析计划生成

**文件：** `agent/think.py`

**注入的变量：** `BASE`, `TARGET`, `DB_BRIEF`

**注入方式：** f-string 直接嵌入

```
{BASE}                    → MD base_knowledge.md + DB base_knowledge 表
{TARGET}                  → MD target_knowledge.md（有内容时注入）
{DB_BRIEF}                → MD db_brief.md
```

**功能：** Think 阶段生成 todo list 分析计划，`BASE` 提供背景知识，`TARGET` 提供目标模板（如有），`DB_BRIEF` 提供数据库概要。

---

### 2. Action 阶段 — 动作决策

**文件：** `agent/action.py`

**注入的变量：** 无（不使用知识库变量）

**注入方式：** 通过 `get_db_summary_for_agent()` 和 `get_func_summary_for_agent()` 动态获取数据库摘要和函数目录

**功能：** Action 阶段决定下一步执行哪个动作，不需要知识库上下文。

---

### 3. Act — explore_schema 子阶段

**文件：** `agent/act.py` → `_act_explore_schema()`

**注入的变量：** `BASE`, `DB_BRIEF`, `DB_QUERY_GUIDE`

**注入方式：** f-string 直接嵌入

```
{BASE}                    → MD base_knowledge.md + DB base_knowledge 表
{DB_BRIEF}                → MD db_brief.md
{DB_QUERY_GUIDE}          → 当前为空（注释状态）
+ full_schema             → 动态查询的数据库结构
```

**功能：** 分析用户问题，筛选出所需的数据库表和字段。

---

### 4. Act — explore_functions 子阶段

**文件：** `agent/act.py` → `_act_explore_functions()`

**注入的变量：** 无（不使用知识库变量）

**注入方式：** 通过 `search_func_by_keyword()` 或 `get_func_catalog_markdown()` 获取函数目录

**功能：** 搜索和筛选可用函数。

---

### 5. Act — generate_and_execute 子阶段（代码生成与执行）

**文件：** `agent/agent.py` → `get_cot_code_prompt()`

**注入的变量：** `BASE`, `TARGET`

**注入方式：** 字符串拼接

```python
cot_prompt = pre_prompt + function_prompt + function_info +
             module_prompt + example_code + remind_prompt +
             database + knowledge + target_section + research_section + question
```

各部分说明：

| 注入内容 | 来源 | 说明 |
|----------|------|------|
| `knowledge` | `BASE` | MD base_knowledge.md + DB base_knowledge 表 |
| `target_section` | `TARGET` | MD target_knowledge.md（有内容时注入） |
| `database` | `get_db_info_prompt()` | 数据库表结构（仅当选择了查询函数时注入） |
| `function_info` | `FUNCTION_DICT` | 选中函数的完整 docstring |
| `research_guide` | Action 阶段传入 | 自然语言描述需要生成的图表和数据 |

**功能：** 生成 Python 代码，调用选中的函数执行数据查询和图表绘制。

---

### 6. Act — generate_document 子阶段（报告生成）

**文件：** `agent/document_generator.py`

**注入的变量：** `BASE`, `DOC`, `TARGET`

**注入方式：** f-string 直接嵌入

```
{BASE}                    → MD base_knowledge.md + DB base_knowledge 表
{DOC}                     → MD doc_knowledge.md + DB doc_knowledge 表
{TARGET}                  → MD target_knowledge.md（有内容时注入）
```

**功能：** 生成业务摘要文档（MD + DOCX）。`DOC` 提供文档格式参考，`BASE` 提供数据背景，`TARGET` 提供目标模板。

---

### 7. Observe 阶段 — 结果审查

**文件：** `agent/observe.py`

**注入的变量：** `TARGET`

**注入方式：** f-string 直接嵌入

```
{TARGET}                  → MD target_knowledge.md（有内容时注入）
```

**功能：** 审查执行结果，判断是否达到目标模板要求，更新 todo list。

---

## 总结：各功能注入的变量

| 功能 | 文件 | 注入变量 | 来源 |
|------|------|----------|------|
| **Think** | `think.py` | `BASE`, `TARGET`, `DB_BRIEF` | MD + DB |
| **Action** | `action.py` | 无（使用 db_summary / func_catalog） | 动态查询 |
| **Act - explore_schema** | `act.py` | `BASE`, `DB_BRIEF`, `DB_QUERY_GUIDE` | MD + DB |
| **Act - explore_functions** | `act.py` | 无（使用 func_catalog） | 动态查询 |
| **Act - generate_and_execute** | `agent.py` | `BASE`, `TARGET`, `database`, `function_info` | MD + DB + 动态查询 |
| **Act - generate_document** | `document_generator.py` | `BASE`, `DOC`, `TARGET` | MD + DB |
| **Observe** | `observe.py` | `TARGET` | MD |
| **（未注入）** | — | `THINK_KNOWLEDGE` | DB |

---

## LLM 搜索流程

`get_*_db_llm()` 函数将查询结果 + 用户上下文发给 LLM，返回结构化结果：

### 事件流格式

```python
yield {"type": "status", "content": "正在分析知识库..."}
yield {"type": "chunk", "content": "LLM 响应的文本片段..."}
yield {"type": "done", "description": "自然语言描述", "useful_ids": [1, 3, 5]}
```

### 可用函数

| 函数 | 说明 |
|------|------|
| `get_base_knowledge_db_llm(context, key)` | 基于 `base_knowledge` 表 + 数据库结构生成查询方案 |
| `get_db_query_guide_db_llm(context, key)` | 基于 `db_query_guide` 表生成 SQL 查询方案 |
| `get_doc_knowledge_db_llm(context, key)` | 基于 `doc_knowledge` 表生成文档分析方案 |
| `get_code_guide_db_llm(context, key)` | 基于 `code_guide` 表生成图表代码方案 |
| `get_think_knowledge_db_llm(context, key)` | 基于 `think_knowledge` 表生成思考分析方案 |

---

## 设置方法

| 函数 | 写入表 | 所在文件 |
|------|--------|----------|
| `set_base_knowledge(text)` | `base_knowledge` | `agent/tools/base_knowledge/set_base_knowledge.py` |
| `set_code_guide(text)` | `code_guide` | `agent/tools/base_knowledge/set_code_guide.py` |
| `set_think_knowledge(text)` | `think_knowledge` | `agent/tools/base_knowledge/set_think_knowledge.py` |

写入后，下一次访问 `BASE` 等变量时自动生效，无需重启。

---

## 数据流图

```
┌──────────────────────────────────────────────────┐
│             启动时加载（缓存）                       │
│  knowledge_docs/*.md  ── _read_doc() ── 缓存变量   │
│                                                  │
│  data_copilot_v10_sys 表 ── get_*_db() ── dict    │
│                                                  │
│           _DynamicStr ── 拼接 MD + DB             │
│                                                  │
│  BASE / DOC / TARGET / DB_BRIEF / DB_QUERY_GUIDE / THINK_KNOWLEDGE  │
└──────────────────────┬───────────────────────────┘
                       │
    ┌──────────┬───────┼───────────┬──────────┐
    ▼          ▼       ▼           ▼          ▼
  Think    explore_  generate_   generate_  Observe
           schema    &execute    document
  {BASE}   {BASE}    knowledge   {BASE}     {TARGET}
  {TARGET} {DB_BRIEF}=BASE       {DOC}
  {DB_BRIEF}         {TARGET}    {TARGET}
```

---

## 相关文件索引

| 文件 | 用途 |
|------|------|
| `agent/tools/base_knowledge/get_base_knowledge.py` | 核心：`_DynamicStr`、`get_*_db()`、`get_*_db_llm()`、模块级变量 |
| `agent/tools/base_knowledge/set_base_knowledge.py` | 写入 `base_knowledge` 表 |
| `agent/tools/base_knowledge/set_code_guide.py` | 写入 `code_guide` 表 |
| `agent/tools/base_knowledge/set_think_knowledge.py` | 写入 `think_knowledge` 表 |
| `agent/tools/base_knowledge/knowledge_docs/` | MD 知识文件目录 |
| `agent/think.py` | Think 阶段 prompt 构建 |
| `agent/action.py` | Action 阶段 prompt 构建 |
| `agent/act.py` | Act 阶段 prompt 构建（explore_schema / explore_functions） |
| `agent/agent.py` | 代码生成阶段 prompt 构建（generate_and_execute） |
| `agent/document_generator.py` | 文档生成阶段 prompt 构建 |
| `agent/observe.py` | Observe 阶段 prompt 构建 |
| `data_access/code_guide_db.py` | `code_guide` 表定义 |
| `data_access/base_knowledge_db.py` | `base_knowledge` 表定义 |
| `data_access/db_query_guide_db.py` | `db_query_guide` 表定义 |
| `data_access/doc_knowledge_db.py` | `doc_knowledge` 表定义 |
| `data_access/think_knowledge_db.py` | `think_knowledge` 表定义 |
| `data_access/sys_db_conn.py` | 系统数据库连接 |
| `docker/docker-init.sql` | 数据库初始化脚本 |
| `main.py` | 启动时创建所有系统表 |