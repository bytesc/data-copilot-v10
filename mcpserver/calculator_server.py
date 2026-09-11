import math
import ast
import operator
from mcp.server import MCPServer

_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.Mod: operator.mod,
}

_ALLOWED_FUNCTIONS = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "sum": sum,
    "pow": pow,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "radians": math.radians,
    "degrees": math.degrees,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "ceil": math.ceil,
    "floor": math.floor,
    "pi": math.pi,
    "e": math.e,
}

mcp = MCPServer("calculator")


def _eval_expression(expr: str) -> float:
    """Safely evaluate a math expression string using AST."""
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError:
        raise ValueError(f"Invalid expression: {expr}")

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"Unsupported constant: {node.value}")
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in _ALLOWED_OPERATORS:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            left = _eval(node.left)
            right = _eval(node.right)
            op_func = _ALLOWED_OPERATORS[op_type]
            result = op_func(left, right)
            if op_type is ast.Div and right == 0:
                raise ValueError("Division by zero")
            return result
        elif isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.USub):
                return -_eval(node.operand)
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        elif isinstance(node, ast.Call):
            func_name = node.func.id if isinstance(node.func, ast.Name) else None
            if func_name not in _ALLOWED_FUNCTIONS:
                raise ValueError(f"Unsupported function: {func_name}")
            args = [_eval(arg) for arg in node.args]
            return _ALLOWED_FUNCTIONS[func_name](*args)
        else:
            raise ValueError(f"Unsupported syntax: {type(node).__name__}")

    result = _eval(tree)
    return float(result)


@mcp.tool()
def calculate(expression: str) -> float:
    """Evaluate a math expression string. Supports basic arithmetic (+, -, *, /, **, %), trigonometric functions (sin, cos, tan), math functions (sqrt, log, log10, exp, ceil, floor, abs, round), and constants (pi, e). Examples: '3 + 5 * 2', 'sqrt(144) + sin(90)', 'log(100, 10)', 'pi * 2'"""
    return _eval_expression(expression)


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8101)