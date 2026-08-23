# 如何新增可用函数（generate_and_execute）

以下步骤说明如何在 `generate_and_execute` 的代码生成阶段中添加新的可用函数。

## 流程概述

```
Think → Action → Act(generate_and_execute) → Code Generation → Code Execution
```

- **Think / Action** 阶段：LLM 通过 `get_func_summary_for_agent()` 看到函数摘要表，决定使用哪些函数。
- **Act 阶段**：`act.py` 将 `selected_functions` 传递给 `agent.py` 中的 `generate_and_execute_stream()`。
- **Code Generation 阶段**：`agent.py` 中的 `get_cot_code_prompt()` 将选中函数的完整 docstring 注入 LLM prompt，LLM 生成带 `def func():` 的 Python 代码。
- **Code Execution 阶段**：`code_executor.py` 通过 `exec()` 执行生成的代码，函数的 import 由 `code_insert.py` 自动注入。

## 步骤概览

| 步骤 | 文件 | 修改内容 |
|------|------|----------|
| 1 | `agent/tools/tools_def.py` | 定义 Python 函数（含 docstring） |
| 2 | `agent/tools/get_function_info.py` | 注册到 `FUNCTION_DICT`、`FUNCTION_IMPORT` |
| 3 | `agent/tools/search_func.py` | 注册到 `FUNC_CATEGORIES`（可选） |
| 4 | `agent/tools/get_function_info.py` | 添加到 `IMPORTANT_FUNC`（可选） |
| 5 | `agent/agent.py` | 检查是否需要更新 prompt 或 import 注入 |

## 详细步骤

### 1. `agent/tools/tools_def.py` — 定义函数

在 `tools_def.py` 中定义新函数，docstring 必须严格遵循以下格式，因为 LLM 通过 docstring 理解函数签名和用途：

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

### docstring 前三行的特殊作用

系统在多个场景下会截取 docstring 前几行，**不按完整 docstring 使用**，因此前三行必须正确填写：

| 场景 | 代码位置 | 截取方式 | 用途 |
|------|----------|----------|------|
| 函数选择（`FUNCTION_DESCRIPTION`） | `get_function_info.py:42` | `splitlines()[1:4]`（第 2~4 行，跳过签名行） | LLM 选择函数时的简短描述 |
| 函数目录（`explore_functions`） | `search_func.py:15` | `splitlines()[1:4]`（同上） | 展示给 LLM 的函数目录 |
| 函数摘要表（`Purpose` 列） | `search_func.py:50` | `splitlines()[3]`（第 4 行） | Think/Action 阶段函数摘要表的 Purpose 列 |
| 代码生成（brief 模式） | `get_function_info.py:85,118` | `splitlines()[:3]`（第 1~3 行，含签名行） | 代码生成 prompt 中的函数简介 |

以 `exe_sql` 为例，其 docstring 各行的使用情况：

```
line 0: exe_sql(sql: str) -> pd.DataFrame:            ← [:3] 时展示，作为函数签名
line 1: Execute the sql query string. Must be used...  ← [1:4] 和 [:3] 时展示，功能描述
line 2: Returns the query results in pandas DataFrame. ← [1:4] 和 [:3] 时展示，返回值描述
line 3: (空行)                                          ← splitlines()[3] 时作为 Purpose（当前为空）
```

> **注意：** 当前所有函数的 `doc_lines[3]`（第 4 行）都是空行，导致摘要表中的 `Purpose` 列为空。如果需要利用 `Purpose` 列，应在第 4 行写一句话描述。

### 2. `agent/tools/get_function_info.py` — 注册函数

**a) 导入函数**（文件顶部）：

```python
from agent.tools.tools_def import my_new_function
```

**b) 添加到 `FUNCTION_DICT`**（约第 5 行）：

```python
FUNCTION_DICT = {
    "exe_sql": exe_sql,
    "load_data": load_data,
    ...
    "my_new_function": my_new_function,   # 新增
}
```

**c) 添加到 `FUNCTION_IMPORT`**（约第 17 行）：

```python
FUNCTION_IMPORT = {
    exe_sql: "from agent.tools.tools_def import exe_sql",
    load_data: "from agent.tools.tools_def import load_data",
    ...
    my_new_function: "from agent.tools.tools_def import my_new_function",   # 新增
}
```

`FUNCTION_IMPORT` 中的字符串会被自动注入到 LLM 生成的代码中，确保代码执行时能正确导入。

### 3. `agent/tools/search_func.py` — 注册分类（可选）

将函数加入 `FUNC_CATEGORIES`（约第 6 行），使其在函数目录中按分类显示：

```python
FUNC_CATEGORIES = {
    "Database": ["exe_sql"],
    "Data Loading": ["load_data"],
    "Visualization": ["get_save_image_path"],
    "Web Search": ["search_web", "fetch_webpage"],
    "My Category": ["my_new_function"],   # 新增
}
```

> 如果不添加到此字典，函数仍然可用，但不会出现在 `explore_functions` 的分类目录中。

### 4. `agent/tools/get_function_info.py` — 设为重要函数（可选）

如果该函数应在每次代码生成时默认可用，添加到 `IMPORTANT_FUNC`（约第 34 行）：

```python
IMPORTANT_FUNC = ["load_data", "get_save_image_path", "my_new_function"]
```

> `IMPORTANT_FUNC` 中的函数始终被包含在 `function_set` 中，即使 LLM 没有明确选择它们。

### 5. `agent/agent.py` — 检查 prompt 和 import 注入

通常不需要修改 `agent.py`，但以下情况需要检查：

- **函数依赖第三方库**：如果新函数使用了 `tools_def.py` 之外的第三方模块，需要在 `agent/agent.py` 中将 import 语句添加到 `IMPORTANT_MODULE` 或 `THIRD_MODULE`（约第 35-36 行），确保生成代码时自动注入。
- **函数需要数据库上下文**：如果函数涉及数据库查询，检查 `agent/agent.py` 中 `get_cot_code_prompt()` 的数据库上下文注入逻辑（约第 74-80 行）。

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

## 示例：新增 `merge_data` 函数

### 1. `tools_def.py`

```python
def merge_data(df1: pd.DataFrame, df2: pd.DataFrame, on: str = "id", how: str = "inner") -> pd.DataFrame:
    """
    merge_data(df1: pd.DataFrame, df2: pd.DataFrame, on: str = "id", how: str = "inner") -> pd.DataFrame:
    将两个 DataFrame 按指定列合并，返回合并后的 DataFrame。
    返回 None 表示出错。

    Args:
    - df1 (pd.DataFrame): 第一个 DataFrame。
    - df2 (pd.DataFrame): 第二个 DataFrame。
    - on (str, optional): 合并列名，默认 "id"。
    - how (str, optional): 合并方式，可选 "inner"、"left"、"right"、"outer"，默认 "inner"。

    Returns:
    - pd.DataFrame: 合并后的数据。
    returns None in case of error

    Example:
    ```python
        result = merge_data(df1, df2, on="user_id", how="left")
        # Output(pd.DataFrame):
        #    user_id  name   age
        # 0  1        Alice  25
    ```
    """
    return pd.merge(df1, df2, on=on, how=how)
```

### 2. `get_function_info.py`

```python
from agent.tools.tools_def import merge_data

FUNCTION_DICT = {
    ...
    "merge_data": merge_data,
}

FUNCTION_IMPORT = {
    ...
    merge_data: "from agent.tools.tools_def import merge_data",
}
```

### 3. `search_func.py`

```python
FUNC_CATEGORIES = {
    ...
    "Data Processing": ["merge_data"],
}
```

## 相关文件索引

| 文件 | 用途 |
|------|------|
| `agent/tools/tools_def.py` | 函数定义实现 |
| `agent/tools/get_function_info.py` | 函数注册表（`FUNCTION_DICT`、`FUNCTION_IMPORT`、`IMPORTANT_FUNC`） |
| `agent/tools/search_func.py` | 函数目录和搜索（`FUNC_CATEGORIES`、`get_func_summary_for_agent`） |
| `agent/agent.py` | 代码生成 prompt 构建（`get_cot_code_prompt`）和执行入口（`generate_and_execute_stream`） |
| `agent/act.py` | 动作分发，`generate_and_execute` 路由到 `_act_generate_and_execute` |
| `agent/tools/copilot/utils/code_executor.py` | 代码执行（`exec()`） |
| `agent/tools/copilot/utils/code_insert.py` | import 注入 |