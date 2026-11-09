# 如何新增可用函数（generate_and_execute）

以下步骤说明如何在 `generate_and_execute` 的代码生成阶段中添加新的可用函数。

## 流程概述

```
Think → Action → Act(generate_and_execute) → Code Generation → Code Execution
```

- **Think / Action** 阶段：`agent/think.py` 与 `agent/action.py` 中虽有 `get_func_summary_for_agent()` 调用，但其结果当前并未注入 Think / Action 的 prompt（死变量）；LLM 实际看到的函数目录来自 `explore_functions` act 提示词中的 `get_func_catalog_markdown()`（`agent/act.py`），以及 `BRIEF_INFO` 中硬编码的 Function Brief（`agent/tools/base_knowledge/get_base_knowledge.py`）。
- **Act 阶段**：`act.py` 将 `selected_fields` 传递给 `agent.py` 中的 `generate_and_execute_stream()`；选中的函数通过 blackboard 的 `functions.selected_functions` 区域传递，由 `get_cot_code_prompt()` 读取（`agent/agent.py`）。
- **Code Generation 阶段**：`agent.py` 中的 `get_cot_code_prompt()` 将选中函数的完整 docstring 注入 LLM prompt，LLM 生成带 `def func():` 的 Python 代码。
- **Code Execution 阶段**：`code_executor.py` 通过 `exec()` 执行生成的代码，函数的 import 由 `code_insert.py` 自动注入。

## 步骤概览

| 步骤 | 文件 | 修改内容 |
|------|------|----------|
| 1 | `agent/tools/tools_def.py`（核心）或 `agent/tools/custom_tools_def.py`（自定义） | 定义 Python 函数（含 docstring） |
| 2 | `agent/tools/get_function_info.py` | 注册到 `FUNCTION_DICT`、`FUNCTION_IMPORT`（自定义函数由 `CUSTOM_FUNC_NAMES` 自动识别） |
| 3 | `agent/tools/search_func.py` | 加入 `_CORE_CATEGORIES` 分类（可选；自定义函数自动进入 `Custom` 分类） |
| 4 | `agent/tools/get_function_info.py` | 添加到 `IMPORTANT_FUNC`（可选） |
| 5 | `agent/agent.py` | 检查是否需要更新 prompt 或 import 注入 |

## 详细步骤

### 1. 定义函数（`agent/tools/tools_def.py` 或 `agent/tools/custom_tools_def.py`）

核心函数定义在 `agent/tools/tools_def.py`；自定义/扩展函数定义在 `agent/tools/custom_tools_def.py`。docstring 必须严格遵循以下格式，因为 LLM 通过 docstring 理解函数签名和用途：

```python
def my_new_function(param1: str, param2: int = 10) -> pd.DataFrame:
    """
    my_new_function(param1: str, param2: int = 10) -> pd.DataFrame:
    对数据执行某种处理操作，返回处理后的 DataFrame。
    返回 None 表示出错。

    Args:
    - param1 (str): 参数1的描述。
    - param2 (int, optional): 参数2的描述，默认 10。

    Returns:
    - pd.DataFrame: 处理后的数据。
    returns None in case of error

    Example:
    ```python
        result = my_new_function("some_value", 20)
        # Output(pd.DataFrame):
        #    col1  col2
        # 0    a     1
    ```
    """
    # 实际实现
    df = do_something(param1, param2)
    return df
```

**关键要求：**
- docstring 第一行必须是函数签名（含参数类型和返回类型）。
- 第二行是功能描述。
- 必须包含 `Args`、`Returns`、`Example` 段落。
- 返回值类型标注要准确，LLM 据此决定如何调用。
- "返回 None 表示出错"（`returns None in case of error`）只是建议约定，**并非强制**：例如 `exe_sql`（`agent/tools/tools_def.py`）采用抛异常风格，docstring 中明确说明出错时不返回 None。各函数按实际行为如实书写即可；上述截取规则只依赖前几行的位置（签名/描述/Returns），不依赖 None 约定。

### docstring 前三行的特殊作用

系统在多个场景下会截取 docstring 前几行，**不按完整 docstring 使用**，因此前三行必须正确填写：

| 场景 | 代码位置 | 截取方式 | 用途 |
|------|----------|----------|------|
| 函数选择（`FUNCTION_DESCRIPTION`） | `get_function_info.py:60-62` | `splitlines()[1:4]`（docstring 以空行开头，故为签名行 + 描述行 + Returns 行） | LLM 选择函数时的简短描述 |
| 函数目录（`get_func_catalog_markdown` / `_get_func_desc`） | `search_func.py:25-26` | `splitlines()[1:4]`（同上） | 展示给 LLM 的函数目录 |
| 函数摘要表（`Purpose` 列） | `search_func.py:60-61` | `splitlines()[3]`（第 4 行，即 Returns 描述行） | Think/Action 阶段函数摘要表的 Purpose 列 |
| 代码生成（brief 模式） | `get_function_info.py:104,135` | `splitlines()[:3]`（第 1~3 行，即空行 + 签名行 + 描述行） | 代码生成 prompt 中的函数简介。brief 模式当前未被调用：唯一的外部调用是 `agent/agent.py` 的 `get_function_info(question, llm, use_all_functions=True)`（brief 默认 False），代码生成实际注入的是完整 docstring |

以 `exe_sql` 为例，其 docstring 各行的使用情况：

```
line 0: (空行)                                          ← 因 docstring 以空行开头，[:3] 时会一并展示
line 1: exe_sql(sql: str) -> pd.DataFrame:            ← [1:4] 和 [:3] 时展示，作为函数签名
line 2: Execute the sql query string. Must be used...  ← [1:4] 和 [:3] 时展示，功能描述
line 3: Returns the query results in pandas DataFrame. ← [1:4] 时展示；splitlines()[3] 时作为 Purpose 列
```

> **注意：** `doc_lines[3]`（第 4 行）是 Returns 描述行，因此摘要表的 `Purpose` 列 **并非为空**，而是显示该行内容。

### 2. `agent/tools/get_function_info.py` — 注册函数

**a) 导入函数**（文件顶部）：

```python
from agent.tools.tools_def import my_new_function
```

> 若函数定义在 `custom_tools_def.py`，改为 `from agent.tools.custom_tools_def import my_new_function`。`CUSTOM_FUNC_NAMES` 通过函数对象的 `__module__` 自动识别自定义函数，无需额外登记。

**b) 添加到 `FUNCTION_DICT`**（约第 6 行）：

```python
FUNCTION_DICT = {
    "exe_sql": exe_sql,
    "load_data": load_data,
    ...
    "my_new_function": my_new_function,   # 新增
}
```

**c) 添加到 `FUNCTION_IMPORT`**（约第 28 行）：

```python
FUNCTION_IMPORT = {
    exe_sql: "from agent.tools.tools_def import exe_sql",
    load_data: "from agent.tools.tools_def import load_data",
    ...
    my_new_function: "from agent.tools.tools_def import my_new_function",   # 新增
}
```

`FUNCTION_IMPORT` 中的字符串会被自动注入到 LLM 生成的代码中，确保代码执行时能正确导入。自定义函数的映射字符串应指向 `agent.tools.custom_tools_def`（例如 `from agent.tools.custom_tools_def import my_new_function`）。

### 3. `agent/tools/search_func.py` — 注册分类（可选）

核心函数的分类定义在 `_CORE_CATEGORIES`（约第 5-10 行），将函数加入对应列表即可在函数目录中按分类显示：

```python
_CORE_CATEGORIES = {
    "Database": ["exe_sql"],
    "Data Loading": ["load_data"],
    "Visualization": ["get_save_image_path"],
    "Web Search": ["search_web", "fetch_webpage"],
    # 新增分类：例如 "My Category": ["my_new_function"]
}
```

> 定义在 `custom_tools_def.py` 的函数无需在此登记：`_get_func_categories()` 会把 `CUSTOM_FUNC_NAMES`（由函数 `__module__` 推导）中未出现在核心分类里的函数自动归入 `Custom` 分类。该分类与 `/api/tools/custom-functions` 接口（只列出 `CUSTOM_FUNC_NAMES` 中的函数）一致。

### 4. `agent/tools/get_function_info.py` — 设为重要函数（可选）

如果该函数应在每次代码生成时默认可用，添加到 `IMPORTANT_FUNC`（`get_function_info.py:53-55`）：

```python
IMPORTANT_FUNC = ["load_data", "get_save_image_path", "my_new_function"]
```

> `IMPORTANT_FUNC` 中的函数始终被包含在 `function_set` 中，即使 LLM 没有明确选择它们。

### 5. `agent/agent.py` — 检查 prompt 和 import 注入

通常不需要修改 `agent.py`，但以下情况需要检查：

- **函数依赖第三方库**：如果新函数使用了 `tools_def.py` 之外的第三方模块，需要在 `agent/agent.py` 中将 import 语句添加到 `IMPORTANT_MODULE` 或 `THIRD_MODULE`（约第 31-40 行），确保生成代码时自动注入。
- **函数需要数据库上下文**：如果函数涉及数据库查询，检查 `agent/agent.py` 中 `get_cot_code_prompt()` 的数据库上下文注入逻辑（`agent.py:115-128`）。

## 函数定义的完整格式规范

```python
def function_name(param1: Type1, param2: Type2 = default) -> ReturnType:
    """
    function_name(param1: Type1, param2: Type2 = default) -> ReturnType:
    一句话功能描述。
    补充说明（可选）。

    Args:
    - param1 (Type1): 参数描述。
    - param2 (Type2, optional): 参数描述，默认值。

    Returns:
    - ReturnType: 返回值描述。
    returns None in case of error

    Example:
    ```python
        result = function_name(arg1, arg2)
        # Output(Type):
        # 示例输出
    ```
    """
    # 实现代码
    return result
```

以上为推荐格式；其中 "returns None in case of error" 是建议约定而非强制（如 `exe_sql` 采用抛异常风格，出错时不返回 None，docstring 如实描述即可）。

## 相关文件索引

| 文件 | 用途 |
|------|------|
| `agent/tools/tools_def.py` | 核心函数定义实现 |
| `agent/tools/custom_tools_def.py` | 自定义函数定义实现（`CUSTOM_FUNC_NAMES` 的来源） |
| `agent/tools/get_function_info.py` | 函数注册表（`FUNCTION_DICT`、`FUNCTION_IMPORT`、`IMPORTANT_FUNC`、`CUSTOM_FUNC_NAMES`） |
| `agent/tools/search_func.py` | 函数目录和搜索（`_CORE_CATEGORIES`、`get_func_summary_for_agent`） |
| `agent/agent.py` | 代码生成 prompt 构建（`get_cot_code_prompt`）和执行入口（`generate_and_execute_stream`） |
| `agent/act.py` | 动作分发，`generate_and_execute` 路由到 `_act_generate_and_execute` |
| `agent/tools/copilot/utils/code_executor.py` | 代码执行（`exec()`） |
| `agent/tools/copilot/utils/code_insert.py` | import 注入 |