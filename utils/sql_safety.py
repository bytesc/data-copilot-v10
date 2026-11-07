"""Shared helpers for building safe MySQL DDL fragments.

These helpers are only meant for identifiers that have already been validated
against the real schema (e.g. via ``sqlalchemy.inspect``). Quoting an
identifier doubles embedded backticks so the name cannot break out of the
identifier quoting.
"""


def quote_ident(name) -> str:
    """Quote a MySQL identifier with backticks, doubling embedded backticks."""
    if not isinstance(name, str) or not name:
        raise ValueError("Invalid SQL identifier")
    return "`" + name.replace("`", "``") + "`"
