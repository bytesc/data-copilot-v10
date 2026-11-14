"""Append-only audit log for the LLM code-execution sandbox.

Every sandbox *start* and every sandbox *refusal* is appended here as one JSON
line, tagged with a timestamp and the request's session id, so an operator can
see after the fact what was run and what the guard blocked:

* ``event="start"`` — a one-shot child process is about to run generated code;
* ``event="deny"``  — the runtime guard refused a file/network access
  (``kind="file_access"`` / ``kind="network_access"``) or the AST review refused
  the code outright (``kind="policy_violation"`` / ``kind="syntax_error"``).

Only the PARENT server process writes this file: the child reports a denial over
the protocol channel and the parent records it, so a denial is logged even when
the generated code silently swallows the ``PermissionError``.

The path is relative to the process working directory (no env vars), matching
``utils/perf_log.py``. Logging is best-effort: a write failure must never break
(or slow down) code execution, so it is swallowed and warned about once.

Toggle with ``enable_sandbox_log`` in ``config/config.yaml`` (default true).
"""

import json
import threading
from datetime import datetime

from agent.utils.get_config import config_data

# Audit log file path, relative to the process working directory (no env vars).
LOG_PATH = "sandbox_audit.log"

_lock = threading.Lock()
_warned = False


def _enabled():
    return bool(config_data.get("enable_sandbox_log", True))


def _now():
    # Millisecond precision, matching the perf log's timestamp format.
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _write(record):
    global _warned
    if not _enabled():
        return
    # ``time`` is set by the caller for a forwarded denial (the moment the guard
    # actually refused) and defaults to now for a locally recorded event.
    record.setdefault("time", _now())
    try:
        line = json.dumps(record, ensure_ascii=False)
    except (TypeError, ValueError):
        return
    try:
        with _lock:
            with open(LOG_PATH, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except OSError as exc:
        if not _warned:
            _warned = True
            print(f"[sandbox_audit] WARNING: failed to write {LOG_PATH}: {exc}")


def record_start(session_id="", run_id="", code=""):
    """Log that a sandbox child is being started for ``session_id``."""
    _write({
        "event": "start",
        "session_id": str(session_id or ""),
        "run_id": str(run_id or ""),
        "code_chars": len(code or ""),
    })


def record_deny(kind, detail, session_id="", run_id="", time=""):
    """Log one sandbox refusal (a guard denial or a policy rejection)."""
    _write({
        "event": "deny",
        "kind": str(kind or ""),
        "detail": str(detail or ""),
        "session_id": str(session_id or ""),
        "run_id": str(run_id or ""),
        "time": str(time) if time else _now(),
    })
