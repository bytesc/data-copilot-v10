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

_TRAILING_COMMENT_RE = re.compile(r"\s+COMMENT\s+'(?:[^']|'')*'\s*$", re.IGNORECASE | re.DOTALL)


def _find_column_definition(create_sql, column_name):
    """Return the full definition line of ``column_name`` from SHOW CREATE TABLE."""
    target = quote_ident(column_name)
    for raw in create_sql.splitlines():
        line = raw.strip()
        if line.startswith(target) and (len(line) == len(target) or line[len(target)].isspace()):
            return line.rstrip(",").rstrip()
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
