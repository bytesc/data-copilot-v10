"""Sandbox child entry point (layers 2, 3 and 5).

Spawned once per execution by ``executor.py`` with ``python -E -s -u runner.py
<job.json>``. It:

1. isolates stdout (the JSON-lines protocol channel) from the generated code's
   own ``print`` output, which is redirected to stderr;
2. configures matplotlib (Agg backend + Chinese font) in a fresh process, so
   figures/rcParams never leak across executions;
3. applies resource limits and starts the orphan watchdog;
4. builds a whitelist namespace (tool functions + pre-imported libraries) and
   ``exec``s the reviewed code there, never in the main process;
5. streams every yielded item back as one JSON line, converting DataFrames to
   CSV.
"""

import json
import os
import sys
import traceback

# Make both this directory (for ``limits``) and the project root importable.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, *([os.pardir] * 5)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Must be set before matplotlib is imported anywhere.
os.environ["MPLBACKEND"] = "Agg"

_PROTOCOL = None


def _setup_protocol():
    """Return a file object for the protocol channel (the real stdout).

    fd 1 is re-pointed at stderr so anything the generated code prints (or any
    library warning) cannot corrupt the protocol; the original stdout is kept on
    a duplicated descriptor.
    """
    fd = os.dup(1)
    os.dup2(2, 1)
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass
    return os.fdopen(fd, "w", encoding="utf-8", buffering=1, newline="\n")


def _emit(obj):
    _PROTOCOL.write(json.dumps(obj, ensure_ascii=False))
    _PROTOCOL.write("\n")
    _PROTOCOL.flush()


def _serialize(item, max_rows, max_bytes):
    import pandas as pd

    if isinstance(item, pd.DataFrame):
        original_rows = int(len(item))
        df = item
        truncated = original_rows > max_rows
        if truncated:
            df = df.head(max_rows)
        csv = df.to_csv()
        while len(csv.encode("utf-8")) > max_bytes and len(df) > 1:
            df = df.head(max(1, len(df) // 2))
            truncated = True
            csv = df.to_csv()
        if len(csv.encode("utf-8")) > max_bytes:
            return {"t": "str", "v": "[DataFrame too large to transfer]"}
        return {"t": "df", "v": csv, "truncated": truncated, "rows": original_rows}

    if isinstance(item, str):
        return {"t": "str", "v": item}
    if item is None or isinstance(item, (bool, int, float)):
        return {"t": "json", "v": item}
    try:
        json.dumps(item, ensure_ascii=False)
        return {"t": "json", "v": item}
    except (TypeError, ValueError):
        return {"t": "str", "v": str(item)}


def _build_namespace():
    import datetime as _datetime
    import json as _json
    import math
    import re as _re

    import matplotlib
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import PIL
    import seaborn as sns

    namespace = {
        "pd": pd, "np": np, "plt": plt, "sns": sns, "PIL": PIL,
        "math": math, "json": _json, "re": _re, "datetime": _datetime,
        "matplotlib": matplotlib,
    }

    # Chinese font for this fresh process only.
    try:
        from agent.tools.copilot.utils.mpl_chinese_font import setup_chinese_font
        setup_chinese_font()
    except Exception:  # pragma: no cover - font is best effort
        pass

    # Never block on a GUI window even though Agg already makes show a no-op.
    try:
        plt.show = lambda *args, **kwargs: None
    except Exception:  # pragma: no cover
        pass

    # Whitelisted tool functions promised to the LLM.
    try:
        from agent.tools.get_function_info import FUNCTION_DICT
        namespace.update(FUNCTION_DICT)
    except Exception as exc:
        _emit({"t": "error", "kind": "environment_error", "msg": f"failed to load tool functions: {exc}"})

    try:
        from agent.tools import tools_def
        for name in ("exe_sql", "load_data", "explain_data",
                     "get_save_image_path", "exe_mcp", "search_web",
                     "fetch_webpage"):
            func = getattr(tools_def, name, None)
            if func is not None:
                namespace.setdefault(name, func)
    except Exception:  # pragma: no cover
        pass

    return namespace


def _apply_llm_selection(selection):
    """Apply the parent request's model/Depth/Style inside this fresh process.

    The contextvars that carry the per-request model selection reset to their
    defaults in a new interpreter, so the LLM-backed tool functions would use the
    first configured model instead of the one the user chose. The parent passes
    the selected values in the job; re-applying them here restores parity.
    Best-effort: an invalid/absent selection falls back to the model defaults.
    """
    if not isinstance(selection, dict):
        return
    try:
        from agent.utils.llm_access.LLM import apply_request_selection
        apply_request_selection(
            selection.get("model"),
            selection.get("reasoning_effort"),
            selection.get("style"),
            selection.get("use_images"),
        )
    except Exception as exc:  # pragma: no cover - selection is best effort
        print(f"[sandbox] WARNING: failed to apply LLM selection: {exc}", flush=True)


def _execute(job):
    code = job.get("code") or ""
    max_rows = int(job.get("max_df_rows") or 50000)
    max_bytes = int(job.get("max_line_mb") or 20) * 1024 * 1024

    _apply_llm_selection(job.get("llm_selection"))
    namespace = _build_namespace()
    try:
        exec(compile(code, "<llm_generated_code>", "exec"), namespace)
        func = namespace.get("func")
        if not callable(func):
            _emit({"t": "error", "kind": "no_func", "msg": "generated code did not define a callable named 'func'"})
            return
        for item in func():
            _emit(_serialize(item, max_rows, max_bytes))
        _emit({"t": "done"})
    except Exception as exc:
        _emit({
            "t": "error",
            "kind": "runtime_error",
            "msg": f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
        })


def main(argv):
    global _PROTOCOL
    _PROTOCOL = _setup_protocol()

    # Fail closed: if anything about the job is unreadable, report and exit.
    try:
        with open(argv[1], "r", encoding="utf-8") as handle:
            job = json.load(handle)
    except Exception as exc:
        _emit({"t": "error", "kind": "job_error", "msg": f"failed to read sandbox job: {exc}"})
        return 1

    limits = job.get("limits") or {}
    import limits as _limits

    _limits.set_process_limits(
        max_memory_mb=limits.get("max_memory_mb"),
        cpu_seconds=limits.get("cpu_seconds"),
        max_processes=limits.get("max_processes"),
        max_file_mb=limits.get("max_file_mb"),
    )
    _limits.start_orphan_watchdog()

    cwd = job.get("project_root")
    if cwd and os.path.isdir(cwd):
        os.chdir(cwd)

    _execute(job)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
