from mcp.server import MCPServer

mcp = MCPServer("text")


@mcp.tool()
def uppercase(text: str) -> str:
    """Convert text to uppercase"""
    return text.upper()


@mcp.tool()
def lowercase(text: str) -> str:
    """Convert text to lowercase"""
    return text.lower()


@mcp.tool()
def reverse(text: str) -> str:
    """Reverse the input text"""
    return text[::-1]


@mcp.tool()
def word_count(text: str) -> int:
    """Count the number of words in text"""
    return len(text.split())


@mcp.tool()
def char_count(text: str) -> int:
    """Count the number of characters in text (excluding spaces)"""
    return len(text.replace(" ", ""))


@mcp.tool()
def concat(a: str, b: str) -> str:
    """Concatenate two strings"""
    return a + b


@mcp.tool()
def contains(text: str, substring: str) -> bool:
    """Check if text contains a substring"""
    return substring in text


@mcp.tool()
def replace(text: str, old: str, new: str) -> str:
    """Replace all occurrences of a substring"""
    return text.replace(old, new)


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8102)