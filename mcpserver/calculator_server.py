import math
from mcp.server import MCPServer

mcp = MCPServer("calculator")


@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers together"""
    return a + b


@mcp.tool()
def subtract(a: float, b: float) -> float:
    """Subtract second number from first number"""
    return a - b


@mcp.tool()
def multiply(a: float, b: float) -> float:
    """Multiply two numbers"""
    return a * b


@mcp.tool()
def divide(a: float, b: float) -> float:
    """Divide first number by second number"""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b


@mcp.tool()
def power(a: float, b: float) -> float:
    """Calculate a raised to the power of b"""
    return a ** b


@mcp.tool()
def sqrt(x: float) -> float:
    """Calculate the square root of a number"""
    if x < 0:
        raise ValueError("Cannot calculate square root of negative number")
    return math.sqrt(x)


@mcp.tool()
def sin(degrees: float) -> float:
    """Calculate sine of an angle in degrees"""
    return round(math.sin(math.radians(degrees)), 10)


@mcp.tool()
def cos(degrees: float) -> float:
    """Calculate cosine of an angle in degrees"""
    return round(math.cos(math.radians(degrees)), 10)


@mcp.tool()
def average(numbers: list[float]) -> float:
    """Calculate the average of a list of numbers"""
    if not numbers:
        raise ValueError("Empty list")
    return sum(numbers) / len(numbers)


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8101)