import sys
from datetime import datetime, timezone, timedelta
from mcp.server import MCPServer

mcp = MCPServer("datetime")


@mcp.tool()
def get_current_time(timezone_offset: str = "+08:00") -> str:
    """Get the current date, time and Unix timestamp with optional timezone offset (e.g. +08:00, -05:00)"""
    print(f"[mcp_datetime] get_current_time(timezone_offset='{timezone_offset}')")
    try:
        sign = 1 if timezone_offset[0] == "+" else -1
        hours, minutes = int(timezone_offset[1:3]), int(timezone_offset[4:6])
        tz = timezone(timedelta(hours=sign * hours, minutes=sign * minutes))
    except Exception as e:
        print(f"[mcp_datetime] get_current_time parse error: {e}", file=sys.stderr)
        tz = timezone.utc
    now = datetime.now(tz)
    result = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    timestamp = int(now.timestamp())
    print(f"[mcp_datetime] get_current_time -> {result}, timestamp={timestamp}")
    return f"{result} (timestamp: {timestamp})"


@mcp.tool()
def weekday(date: str) -> str:
    """Get the day of the week for a given date (YYYY-MM-DD)"""
    print(f"[mcp_datetime] weekday(date='{date}')")
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        result = dt.strftime("%A")
        print(f"[mcp_datetime] weekday -> {result}")
        return result
    except Exception as e:
        print(f"[mcp_datetime] weekday error: {e}", file=sys.stderr)
        raise


@mcp.tool()
def add_days(date: str, days: int) -> str:
    """Add a number of days to a date (can be negative); returns YYYY-MM-DD"""
    print(f"[mcp_datetime] add_days(date='{date}', days={days})")
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        result = dt + timedelta(days=days)
        result_str = result.strftime("%Y-%m-%d")
        print(f"[mcp_datetime] add_days -> {result_str}")
        return result_str
    except Exception as e:
        print(f"[mcp_datetime] add_days error: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8103)