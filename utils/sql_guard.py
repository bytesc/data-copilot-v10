"""Read-only SQL guard.

The ``exe_sql`` path (and the NL->SQL / ``/api/exe-sql/`` paths that share
``execute_select``) must never mutate the user database.  LLM-generated SQL can
otherwise contain ``DROP`` / ``DELETE`` / ``UPDATE`` / ``ALTER`` and destroy data
that MySQL commits implicitly.  This module rejects anything that is not a
single read-only statement before it reaches the driver.

It is a best-effort application-layer guard, not a security boundary: generated
code can still reach the engine directly.  Use a SELECT-only database account
(see config ``mysql_readonly``) as the real boundary.
"""

import re

# Only these statement heads are accepted.  SHOW / DESCRIBE / EXPLAIN are
# intentionally excluded ("SELECT only"); add them here if metadata reads are
# ever needed through this path.
_ALLOWED_STARTS = {"SELECT", "WITH"}

_LEADING_COMMENT_RE = re.compile(
    r"^\s*(?:(?:--[^\n]*\n)|(?:\#[^\n]*\n)|(?:/\*.*?\*/))+", re.DOTALL
)
_TRAILING_COMMENT_RE = re.compile(
    r"(?:(?:--[^\n]*)|(?:\#[^\n]*)|(?:/\*.*?\*/))\s*$", re.DOTALL
)

# MySQL supports ``WITH ... UPDATE/DELETE``, so CTE queries are additionally
# scanned for write keywords.
_WRITE_KEYWORDS_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|REPLACE|MERGE|DROP|ALTER|TRUNCATE|CREATE|RENAME|"
    r"GRANT|REVOKE|CALL|SET|LOAD|HANDLER|LOCK|UNLOCK|COMMIT|ROLLBACK|"
    r"SAVEPOINT|START|BEGIN|USE|EXECUTE|PREPARE|DEALLOCATE)\b",
    re.IGNORECASE,
)

# Read-only SELECTs that still have side effects on the server/filesystem.
_DANGEROUS_CLAUSES_RE = re.compile(
    r"\bINTO\s+(OUTFILE|DUMPFILE)\b"
    r"|\bLOAD_FILE\s*\("
    r"|\bFOR\s+UPDATE\b"
    r"|\bLOCK\s+IN\s+SHARE\s+MODE\b",
    re.IGNORECASE,
)

# Strip string literals before keyword scanning so values like 'drop' do not
# trigger a false positive.
_STRING_LITERAL_RE = re.compile(
    r"'(?:[^'\\]|\\.|'')*'" r'|"(?:[^"\\]|\\.|"")*"'
)


def assert_read_only_sql(sql):
    """Return the normalized statement, or raise ``ValueError`` if not read-only."""
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("Empty SQL statement")

    body = _LEADING_COMMENT_RE.sub("", sql).strip()
    body = _TRAILING_COMMENT_RE.sub("", body).strip()
    body = body.rstrip(";").strip()
    if not body:
        raise ValueError("Empty SQL statement")
    if ";" in body:
        raise ValueError(
            "Multiple SQL statements are not allowed; run one statement at a time."
        )

    match = re.match(r"([A-Za-z]+)", body)
    first = match.group(1).upper() if match else ""
    if first not in _ALLOWED_STARTS:
        raise ValueError(
            f"Only read-only SQL (SELECT) is allowed; refusing to run "
            f"'{first or sql.strip()[:30]}'."
        )

    scanned = _STRING_LITERAL_RE.sub("''", body)
    if first == "WITH" and _WRITE_KEYWORDS_RE.search(scanned):
        raise ValueError(
            "Only read-only SQL is allowed; data-modifying statements are not permitted."
        )
    if _DANGEROUS_CLAUSES_RE.search(scanned):
        raise ValueError(
            "This SELECT clause is not allowed "
            "(INTO OUTFILE / DUMPFILE / LOAD_FILE / row locking)."
        )
    return body
