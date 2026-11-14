"""Build safe MySQL comment DDL while preserving the original column definition.

MySQL can only change a column comment through ``ALTER TABLE ... MODIFY COLUMN``,
which requires the *complete* column definition. Rebuilding that definition from
``inspect().get_columns()`` loses attributes such as ``AUTO_INCREMENT``,
``ON UPDATE CURRENT_TIMESTAMP``, ``CHARACTER SET/COLLATE`` and generated-column
expressions. Instead we read the exact definition from ``SHOW CREATE TABLE`` and
only replace its trailing ``COMMENT`` clause.

The comment value is escaped according to the current session ``sql_mode`` so it
is correct both with the default backslash escaping and with
``NO_BACKSLASH_ESCAPES``. Statements are executed by the caller via
``exec_driver_sql`` so SQLAlchemy never mis-parses ``:`` characters that can
appear inside defaults such as ``DEFAULT '12:30:00'``.
"""

import re

from utils.sql_safety import quote_ident

# MySQL renders an existing comment literal with backslash escaping by default
# (e.g. ``COMMENT 'it\'s'``) and with doubled quotes under NO_BACKSLASH_ESCAPES.
# Handle both, plus escaped backslashes, so the old trailing COMMENT is always
# stripped before the replacement is appended (otherwise two COMMENT clauses are
# emitted and the ALTER fails).
_TRAILING_COMMENT_RE = re.compile(r"\s+COMMENT\s+'(?:[^'\\]|\\.|'')*'\s*$", re.IGNORECASE | re.DOTALL)


def _create_table_body(create_sql):
    """Return the text between the outermost parentheses of a CREATE TABLE.

    The opening parenthesis is located with quote awareness (backtick-quoted
    identifiers and string literals are skipped), and its matching close is found
    by tracking nesting depth, so a column definition that itself contains
    parentheses (e.g. ``DEFAULT (uuid())``) does not end the body early.
    """
    if not isinstance(create_sql, str):
        return None
    depth = 0
    body_start = None
    quote = None
    i = 0
    n = len(create_sql)
    while i < n:
        ch = create_sql[i]
        if quote is not None:
            if ch == quote:
                if i + 1 < n and create_sql[i + 1] == quote:
                    i += 2
                    continue
                quote = None
            elif ch == "\\" and quote in ("'", '"'):
                i += 2
                continue
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            continue
        if ch == "(":
            if depth == 0:
                body_start = i + 1
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and body_start is not None:
                return create_sql[body_start:i]
        i += 1
    return None


def _split_top_level(body):
    """Split a CREATE TABLE body on top-level commas.

    Commas inside parentheses, backtick-quoted identifiers and string literals
    are ignored, so a multi-line column definition (e.g. a comment containing a
    newline, or a generated-column expression) is kept in one piece instead of
    being cut at its first physical line.
    """
    parts = []
    current = []
    depth = 0
    quote = None
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if quote is not None:
            current.append(ch)
            if ch == quote:
                if i + 1 < n and body[i + 1] == quote:
                    current.append(body[i + 1])
                    i += 2
                    continue
                quote = None
            elif ch == "\\" and quote in ("'", '"'):
                if i + 1 < n:
                    current.append(body[i + 1])
                    i += 2
                    continue
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            current.append(ch)
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    parts.append("".join(current))
    return parts


def _find_column_definition(create_sql, column_name):
    """Return the full column definition of ``column_name`` from SHOW CREATE TABLE.

    The definition is returned in full even when it spans multiple lines (a
    comment containing a newline, a generated-column expression, ...), so
    ``MODIFY COLUMN`` never receives a truncated definition. Only a definition
    whose leading token is the quoted column name matches; table-level clauses
    (``PRIMARY KEY``, ``KEY``, ``CONSTRAINT``, ...) never start with a backtick
    and are therefore skipped.
    """
    target = quote_ident(column_name)
    body = _create_table_body(create_sql)
    if body is None:
        return None
    for item in _split_top_level(body):
        stripped = item.strip()
        if stripped.startswith(target) and (
            len(stripped) == len(target) or stripped[len(target)].isspace()
        ):
            return stripped
    return None


def _session_escape(conn, value):
    """Escape a value for a single-quoted literal using the session sql_mode."""
    if value is None:
        return ""
    mode = str(conn.exec_driver_sql("SELECT @@SESSION.sql_mode").scalar() or "").upper()
    text_value = str(value)
    if "NO_BACKSLASH_ESCAPES" in mode:
        return text_value.replace("'", "''")
    return text_value.replace("\\", "\\\\").replace("'", "''")


def build_column_comment_sql(conn, table_name, column_name, comment):
    """Return SQL that sets a column comment, preserving every other attribute."""
    create_sql = conn.exec_driver_sql(
        f"SHOW CREATE TABLE {quote_ident(table_name)}"
    ).fetchone()[1]
    definition = _find_column_definition(create_sql, column_name)
    if definition is None:
        raise ValueError(f"Column '{column_name}' not found in '{table_name}'")
    definition = _TRAILING_COMMENT_RE.sub("", definition)
    return (
        f"ALTER TABLE {quote_ident(table_name)} MODIFY COLUMN {definition} "
        f"COMMENT '{_session_escape(conn, comment)}'"
    )


def build_table_comment_sql(conn, table_name, comment):
    """Return SQL that sets a table comment with a sql_mode-safe literal."""
    return (
        f"ALTER TABLE {quote_ident(table_name)} "
        f"COMMENT = '{_session_escape(conn, comment)}'"
    )
