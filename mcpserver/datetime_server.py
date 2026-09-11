import sys
from datetime import datetime, timezone, timedelta
from mcp.server import MCPServer

mcp = MCPServer("datetime")


@mcp.tool()
def get_current_time(timezone_offset: str = "+00:00") -> str:
    """Get the current date and time with optional timezone offset (e.g. +08:00, -05:00)"""
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
    print(f"[mcp_datetime] get_current_time -> {result}")
    return result


@mcp.tool()
def format_date(date: str, format: str = "%Y-%m-%d") -> str:
    """Format a date string. Input can be YYYY-MM-DD, YYYY/MM/DD, or MM/DD/YYYY"""
    print(f"[mcp_datetime] format_date(date='{date}', format='{format}')")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(date, fmt)
            result = dt.strftime(format)
            print(f"[mcp_datetime] format_date -> {result}")
            return result
        except ValueError:
            continue
    print(f"[mcp_datetime] format_date error: unable to parse '{date}'", file=sys.stderr)
    return f"Unable to parse date: {date}"


@mcp.tool()
def date_diff(start: str, end: str) -> int:
    """Calculate the difference in days between two dates (YYYY-MM-DD)"""
    print(f"[mcp_datetime] date_diff(start='{start}', end='{end}')")
    try:
        s = datetime.strptime(start, "%Y-%m-%d")
        e = datetime.strptime(end, "%Y-%m-%d")
        result = abs((e - s).days)
        print(f"[mcp_datetime] date_diff -> {result}")
        return result
    except Exception as e:
        print(f"[mcp_datetime] date_diff error: {e}", file=sys.stderr)
        raise


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
def timestamp() -> int:
    """Get current Unix timestamp (seconds since epoch)"""
    print(f"[mcp_datetime] timestamp()")
    try:
        result = int(datetime.now().timestamp())
        print(f"[mcp_datetime] timestamp -> {result}")
        return result
    except Exception as e:
        print(f"[mcp_datetime] timestamp error: {e}", file=sys.stderr)
        raise


@mcp.tool()
def add_days(date: str, days: int) -> str:
    """Add a number of days to a date (can be negative)"""
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