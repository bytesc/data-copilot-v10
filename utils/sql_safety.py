"""Shared helpers for building safe MySQL DDL fragments.

These helpers are only meant for identifiers/values that have already been
validated against the real schema (e.g. via ``sqlalchemy.inspect``). Quoting an
identifier doubles embedded backticks, and escaping a value doubles backslashes
(MySQL's default escape character) and single quotes. Backslashes must be
escaped first.

MySQL DDL such as ``ALTER TABLE ... COMMENT '<x>'`` cannot use bound
parameters, so escaping is the defense here.
"""


def quote_ident(name) -> str:
    """Quote a MySQL identifier with backticks, doubling embedded backticks."""
    if not isinstance(name, str) or not name:
        raise ValueError("Invalid SQL identifier")
    return "`" + name.replace("`", "``") + "`"


def escape_string(value) -> str:
    """Escape a value for use inside a single-quoted MySQL string literal."""
    if value is None:
        return ""
    return str(value).replace("\\", "\\\\").replace("'", "''")
