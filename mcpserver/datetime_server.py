import sys
from datetime import datetime, timezone, timedelta
from mcp.server import MCPServer

mcp = MCPServer("datetime")


@mcp.tool()
def get_current_time(timezone_offset: str = "+00:00") -> str:
    """Get the current date and time with optional timezone offset (e.g. +08:00, -05:00)"""
    try:
        sign = 1 if timezone_offset[0] == "+" else -1
        hours, minutes = int(timezone_offset[1:3]), int(timezone_offset[4:6])
        tz = timezone(timedelta(hours=sign * hours, minutes=sign * minutes))
    except Exception as e:
        print(f"[datetime_server] Invalid timezone_offset '{timezone_offset}': {e}", file=sys.stderr)
        tz = timezone.utc
    now = datetime.now(tz)
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")


@mcp.tool()
def format_date(date: str, format: str = "%Y-%m-%d") -> str:
    """Format a date string. Input can be YYYY-MM-DD, YYYY/MM/DD, or MM/DD/YYYY"""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(date, fmt)
            return dt.strftime(format)
        except ValueError:
            continue
    print(f"[datetime_server] Unable to parse date: {date}", file=sys.stderr)
    return f"Unable to parse date: {date}"


@mcp.tool()
def date_diff(start: str, end: str) -> int:
    """Calculate the difference in days between two dates (YYYY-MM-DD)"""
    try:
        s = datetime.strptime(start, "%Y-%m-%d")
        e = datetime.strptime(end, "%Y-%m-%d")
        return abs((e - s).days)
    except Exception as e:
        print(f"[datetime_server] date_diff error: start='{start}' end='{end}': {e}", file=sys.stderr)
        raise


@mcp.tool()
def weekday(date: str) -> str:
    """Get the day of the week for a given date (YYYY-MM-DD)"""
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        return dt.strftime("%A")
    except Exception as e:
        print(f"[datetime_server] weekday error: date='{date}': {e}", file=sys.stderr)
        raise


@mcp.tool()
def timestamp() -> int:
    """Get current Unix timestamp (seconds since epoch)"""
    try:
        return int(datetime.now().timestamp())
    except Exception as e:
        print(f"[datetime_server] timestamp error: {e}", file=sys.stderr)
        raise


@mcp.tool()
def add_days(date: str, days: int) -> str:
    """Add a number of days to a date (can be negative)"""
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        result = dt + timedelta(days=days)
        return result.strftime("%Y-%m-%d")
    except Exception as e:
        print(f"[datetime_server] add_days error: date='{date}' days={days}: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8103)