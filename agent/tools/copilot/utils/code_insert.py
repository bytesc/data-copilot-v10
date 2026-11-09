import ast
import re

def insert_yield_statements(code):
    # 去除所有空行
    code = '\n'.join([line for line in code.split('\n') if line.strip()])
    # 使用正则表达式匹配赋值语句，考虑行首的空白字符
    assignment_pattern = re.compile(r'^(\s*)(\w+)\s*=\s', re.MULTILINE)
    # 使用正则表达式匹配yield语句，考虑行首的空白字符
    yield_pattern = re.compile(r'^(\s*)yield\s+(\w+)', re.MULTILINE)

    lines = code.split('\n')
    new_lines = []

    # 创建一个集合来跟踪已经yield过的变量
    yielded_variables = set()
    for i in range(len(lines)):
        line = lines[i]
        yield_match = yield_pattern.match(line)
        if yield_match:
            variable_name = yield_match.group(2)
            yielded_variables.add(variable_name)

    for i in range(len(lines)):
        line = lines[i]
        new_lines.append(line)

        # 检查当前行是否是赋值语句
        assignment_match = assignment_pattern.match(line)
        if assignment_match:
            indentation, variable_name = assignment_match.groups()
            # 检查下一行是否是yield该变量的语句
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                yield_match = yield_pattern.match(next_line)
                # 如果下一行不是yield该变量的语句，或者还没有yield过该变量
                if not yield_match or yield_match.group(2) != variable_name:
                    # 并且该变量还没有被yield过
                    if variable_name not in yielded_variables:
                        # 插入yield语句，保持相同的缩进
                        new_lines.append(f"{indentation}yield {variable_name}")
                        # 将变量添加到已yield的集合中
                        yielded_variables.add(variable_name)

        # 检查当前行是否是yield语句
        yield_match = yield_pattern.match(line)
        if yield_match:
            variable_name = yield_match.group(2)
            # 将变量添加到已yield的集合中
            yielded_variables.add(variable_name)

    return '\n'.join(new_lines)


_DEF_FUNC_LINE_RE = re.compile(r'^([ \t]*)def[ \t]+func[ \t]*\(')


def _body_insert_index(lines):
    """Return ``(index, indent)`` for injecting lines at the top of ``func``'s body.

    Injections go right at the start of the function body, but AFTER a leading
    docstring so the docstring keeps its special meaning (a statement placed
    before it turns the docstring into a no-op string literal).

    The function is located structurally via ``ast`` (not by the first
    substring match of ``'def func('``, which could land in a comment or
    string). If the source cannot be parsed, fall back to the first line that
    starts a top-level ``def func(`` definition.
    """
    try:
        tree = ast.parse('\n'.join(lines))
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in tree.body:
            if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == 'func' and node.body):
                first = node.body[0]
                if (isinstance(first, ast.Expr)
                        and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)):
                    idx = first.end_lineno  # line after the docstring (1-based -> next index)
                else:
                    idx = first.lineno - 1
                if 0 <= idx <= len(lines):
                    indent_match = re.match(r'^[ \t]*', lines[first.lineno - 1])
                    indent = indent_match.group(0) if indent_match else '    '
                    return idx, indent

    for i, line in enumerate(lines):
        match = _DEF_FUNC_LINE_RE.match(line)
        if match:
            return i + 1, match.group(1) + '    '
    return None, None


def insert_lines_into_function(code_str: str, lines_to_insert: list) -> str:
    if not lines_to_insert:
        return code_str

    lines = code_str.split('\n')
    insert_index, indent = _body_insert_index(lines)
    if insert_index is None:
        # No `def func(` found: return the original string untouched.
        return code_str

    injected = [indent + line for line in lines_to_insert]
    return '\n'.join(lines[:insert_index] + injected + lines[insert_index:])


if __name__=="__main__":
    # 示例代码
    original_code = """
def func(data: pd):
    import pandas as pd
    from agent.tools.tools_def import exe_sql
    import math

    yield "正在查询LORONG 7 TOA PAYOH的位置信息..."
    toa_payoh_location = exe_sql("SELECT latitude, longitude FROM toa_payoh LIMIT 1")
    """
    lines_to_insert = ["import pandas as pd", "import math"]

    # 调用函数并打印结果
    modified_code = insert_lines_into_function(original_code, lines_to_insert)
    print(modified_code)

