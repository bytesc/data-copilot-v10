"""Main-process side of the sandbox (layer 2 orchestration + layers 3-5 glue).

Responsibilities:

* run the AST review (:mod:`policy`) and refuse to execute rejected code;
* spawn a one-shot child (``python -E -s -u runner.py <job>``) with a minimal
  environment whose config is rendered per run from the main config, with the
  database credentials replaced by the read-only account;
* read the child's JSON-lines protocol with an overall deadline and hard-kill the
  whole process tree on timeout;
* decode DataFrame/str/json items back for the existing SSE pipeline.

Calling :func:`execute_in_sandbox` returns a generator, so the child process is
only started when the caller starts iterating (and is killed if iteration stops
early). There is deliberately NO in-process execution fallback.
"""

import io
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import yaml

from agent.utils.get_config import config_data
from config.sandbox_config import get_section

from .limits import IS_WINDOWS, WindowsJob, kill_tree
from .policy import PolicyViolation, validate

_HERE = Path(__file__).resolve().parent          # .../utils/sandbox
_PROJECT_ROOT = _HERE.parents[4]                 # project root
_RUNNER = _HERE / "runner.py"


class SandboxError(RuntimeError):
    """Raised when generated code is rejected, times out or fails in the child.

    ``kind`` is a stable machine-readable code for the failure category, so the
    caller can record it, show it and feed it back to the LLM instead of having
    to parse prose. Known kinds:

    * ``policy_violation``  - rejected by the AST review (the code is NOT run);
    * ``syntax_error``      - generated code is not valid Python;
    * ``timeout``           - exceeded the wall-clock sandbox limit;
    * ``resource_limit``    - child killed by a resource cap (memory / CPU /
      file size) or crashed before finishing;
    * ``no_func``           - code did not define a callable named ``func``;
    * ``runtime_error``     - generated code raised while executing;
    * ``environment_error`` - sandbox/tool setup failed before running the code;
    * ``job_error``         - the sandbox job file could not be read;
    * ``config_error``      - the minimal sandbox config could not be rendered.
    """

    def __init__(self, message, kind="sandbox_error", **details):
        super().__init__(message)
        self.kind = kind
        self.details = details


def _config():
    # Resource limits come entirely from config/sandbox.yaml (no in-code
    # defaults); a missing key is reported as a config error.
    code_exec = get_section("code_exec")
    required = ("timeout", "max_memory_mb", "cpu_rate", "max_processes",
                "max_file_mb", "max_df_rows", "max_line_mb")
    missing = [key for key in required if key not in code_exec]
    if missing:
        raise SandboxError(
            "sandbox config 'code_exec' is missing required keys: "
            + ", ".join(missing),
            kind="config_error",
        )
    return {
        "timeout": float(code_exec["timeout"]),
        "max_memory_mb": int(code_exec["max_memory_mb"]),
        "cpu_seconds": int(code_exec["cpu_rate"]),
        "max_processes": int(code_exec["max_processes"]),
        "max_file_mb": int(code_exec["max_file_mb"]),
        "max_df_rows": int(code_exec["max_df_rows"]),
        "max_line_mb": int(code_exec["max_line_mb"]),
    }


def _url_endpoint(url):
    """Return ``(host, port)`` from a URL (either may be None)."""
    try:
        parsed = urlparse(str(url or ""))
        return parsed.hostname, parsed.port
    except Exception:
        return None, None


def _mcp_sse_endpoints():
    """(host, port) of configured SSE MCP servers (stdio servers need no network)."""
    endpoints = []
    try:
        with open(os.path.join(_PROJECT_ROOT, "config", "mcp_servers.yaml"),
                  "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        for srv in (data.get("mcp_servers") or []):
            if str(srv.get("transport", "stdio")) == "sse":
                endpoints.append(_url_endpoint(srv.get("url")))
    except Exception:
        pass
    return endpoints


def _guard_config():
    """Assemble the runtime file-access / network guard config for the child.

    Starts from ``sandbox.yaml`` (``file_access`` + ``network``) and augments the
    network allow-list with the hosts/ports the whitelisted tools must be able to
    reach: the read-only database, every configured LLM API and every SSE MCP
    server. This keeps the operator from having to list them by hand while still
    denying every other destination.
    """
    file_access = get_section("file_access")
    network = dict(get_section("network"))

    hosts = list(network.get("allow_hosts") or [])
    ports = list(network.get("allow_ports") or [])

    endpoints = [_url_endpoint(config_data.get("mysql_readonly"))]
    endpoints += [_url_endpoint(m.get("url")) for m in (config_data.get("llm_models") or [])]
    endpoints += _mcp_sse_endpoints()
    for host, port in endpoints:
        if host and host not in hosts:
            hosts.append(host)
        if port is not None and port not in ports:
            ports.append(port)

    network["allow_hosts"] = hosts
    network["allow_ports"] = ports
    return {"file_access": file_access, "network": network}


def _current_llm_selection():
    """Snapshot the current request's model selection for the sandbox child.

    The child process is a fresh interpreter whose contextvars start at their
    defaults (the first configured model), so the LLM-backed tool functions it
    runs (``explain_data``, ``predict_hdb_price``) would otherwise ignore the
    model/Depth/Style the user picked. The values are read here, at spawn time
    inside the request's context, and forwarded to the child via the job file.
    Best-effort: if the selection cannot be read, the child keeps its defaults.
    """
    try:
        from agent.utils.llm_access.LLM import (
            get_current_model_id,
            get_current_reasoning_effort,
            get_current_style,
            get_current_use_images,
        )
        return {
            "model": get_current_model_id(),
            "reasoning_effort": get_current_reasoning_effort(),
            "style": get_current_style(),
            "use_images": get_current_use_images(),
        }
    except Exception:
        return {}


_ENV_ALLOW = (
    "PATH", "PATHEXT", "SYSTEMROOT", "SystemRoot", "WINDIR", "COMSPEC",
    "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
    "PROGRAMDATA", "NUMBER_OF_PROCESSORS", "LANG", "LC_ALL", "TZ", "OS",
)


def _build_env(sandbox_config_path):
    env = {key: os.environ[key] for key in _ENV_ALLOW if key in os.environ}
    env["MPLBACKEND"] = "Agg"
    if sandbox_config_path:
        env["CODE_EXEC_CONFIG"] = str(sandbox_config_path)
    return env


def _render_sandbox_config(workdir):
    """Write a minimal, standalone config for the sandbox child process.

    The child is independent of the main config: it is given ONLY the values its
    whitelisted tool functions actually read, and nothing else. Concretely:

    * ``mysql_readonly`` - the read-only database URL (the only database identity
      the sandbox needs; the privileged ``mysql`` / ``mysql_sys`` engines are not
      used here and are therefore never provided);
    * ``static_path``    - the base URL used to build image/CSV links;
    * ``llm_models``     - model metadata needed by the LLM-backed tools
      (explain_data, predict_hdb_price) to build their request parameters. No
      API key is included: the child does not create a real client or read a key
      file — every LLM call is proxied back to the parent (see ``runner.py``).

    Privileged and irrelevant keys are neither copied nor touched, so no
    privileged credential and no unused setting ever reaches the child. Fails
    closed: if the file cannot be written, the caller aborts rather than letting
    the child fall back to the privileged ``config.yaml``.
    """
    data = {
        "mysql_readonly": config_data.get("mysql_readonly") or "",
        "static_path": config_data.get("static_path", ""),
        "llm_models": config_data.get("llm_models") or [],
    }

    path = os.path.join(workdir, "sandbox_config.yaml")
    try:
        with open(path, "w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, allow_unicode=True,
                           default_flow_style=False, sort_keys=False)
    except (OSError, yaml.YAMLError) as exc:
        raise SandboxError(
            f"failed to render the sandbox config: {exc}", kind="config_error"
        ) from exc
    return path


def _pump(stream, sink):
    try:
        for line in iter(stream.readline, b""):
            sink.put(("line", line))
    except Exception:
        pass
    finally:
        sink.put(("eof", None))


def _decode(raw):
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def _deserialize(message):
    kind = message.get("t")
    if kind == "df":
        text = message.get("v", "")
        try:
            return pd.read_csv(io.StringIO(text), index_col=0)
        except Exception:
            return pd.read_csv(io.StringIO(text))
    if kind == "json":
        return message.get("v")
    return message.get("v", "")


def _read_tail(path, limit=4000):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            data = handle.read()
    except OSError:
        return ""
    return data[-limit:]


def _cleanup(path):
    shutil.rmtree(path, ignore_errors=True)


def _handle_llm_request(message):
    """Run one proxied LLM call in the PARENT, which owns the API key.

    The child never holds the key; it forwards the request here and receives the
    answer text back. This keeps the key out of the (untrusted) child process.
    """
    from agent.utils.llm_access.LLM import get_llm_dynamic

    payload = message.get("payload") or {}
    try:
        response = get_llm_dynamic().chat.completions.create(**payload)
        content = response.choices[0].message.content
        return {"t": "llm_response", "id": message.get("id"), "ok": True, "content": content}
    except Exception as exc:
        return {
            "t": "llm_response",
            "id": message.get("id"),
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _write_child(proc, obj):
    try:
        proc.stdin.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        proc.stdin.flush()
    except Exception:
        pass


def execute_in_sandbox(code):
    """Validate ``code`` and return a generator over its deserialized results.

    Policy violations raise immediately (before any process is started) so the
    caller can feed the message back to the LLM. Otherwise the returned generator
    lazily starts a one-shot child when first iterated.
    """
    try:
        violations = validate(code)
    except PolicyViolation as exc:
        raise SandboxError(
            "Generated code was rejected by the sandbox security policy and was "
            f"NOT executed:\n  - {exc}\nPlease regenerate the code without it.",
            kind=getattr(exc, "kind", "policy_violation"),
        ) from exc
    if violations:
        bullets = "\n".join(f"  - {item}" for item in violations)
        raise SandboxError(
            "Generated code was rejected by the sandbox security policy and was "
            f"NOT executed:\n{bullets}\n"
            "Remove the disallowed imports/calls and regenerate the code.",
            kind="policy_violation",
        )
    return _iter_items(code)


def _iter_items(code):
    cfg = _config()
    job = {
        "code": code,
        "project_root": str(_PROJECT_ROOT),
        "max_df_rows": cfg["max_df_rows"],
        "max_line_mb": cfg["max_line_mb"],
        "llm_selection": _current_llm_selection(),
        "guard": _guard_config(),
        "limits": {
            "timeout": cfg["timeout"],
            "max_memory_mb": cfg["max_memory_mb"],
            "cpu_seconds": cfg["cpu_seconds"],
            "max_processes": cfg["max_processes"],
            "max_file_mb": cfg["max_file_mb"],
        },
    }

    workdir = tempfile.mkdtemp(prefix="code_sandbox_")
    try:
        sandbox_config_path = _render_sandbox_config(workdir)
    except Exception:
        _cleanup(workdir)
        raise
    job_path = os.path.join(workdir, "job.json")
    err_path = os.path.join(workdir, "stderr.log")
    with open(job_path, "w", encoding="utf-8") as handle:
        json.dump(job, handle, ensure_ascii=False)

    err_handle = open(err_path, "w", encoding="utf-8", errors="replace")
    command = [sys.executable, "-E", "-s", "-u", str(_RUNNER), job_path]
    popen_kwargs = dict(
        cwd=str(_PROJECT_ROOT),
        env=_build_env(sandbox_config_path),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=err_handle,
    )
    if IS_WINDOWS:
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    job_object = WindowsJob(cfg["max_memory_mb"]) if IS_WINDOWS else None
    sink = queue.Queue()
    proc = None
    reader = None
    try:
        proc = subprocess.Popen(command, **popen_kwargs)
        if job_object is not None:
            job_object.assign(proc.pid)
        reader = threading.Thread(
            target=_pump, args=(proc.stdout, sink),
            name="sandbox-reader", daemon=True,
        )
        reader.start()

        deadline = time.monotonic() + cfg["timeout"]
        finished = False
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SandboxError(_timeout_message(cfg, err_path), kind="timeout")
            try:
                kind, raw = sink.get(timeout=remaining)
            except queue.Empty:
                raise SandboxError(_timeout_message(cfg, err_path), kind="timeout")

            if kind == "eof":
                break
            message = _decode(raw)
            if message is None:
                continue
            if message.get("t") == "llm_request":
                # Proxied LLM call: run it here (parent holds the key) and reply.
                _write_child(proc, _handle_llm_request(message))
                continue
            if message.get("t") == "error":
                tail = _read_tail(err_path)
                msg = message.get("msg") or "sandbox execution error"
                if tail:
                    msg = f"{msg}\n--- sandbox stderr (tail) ---\n{tail}"
                raise SandboxError(msg, kind=message.get("kind") or "runtime_error")
            if message.get("t") == "done":
                finished = True
                break
            yield _deserialize(message)

        if not finished:
            # The child vanished without a terminal message: killed by a resource
            # limit (memory/CPU/file size) or crashed. Surface it as an error so
            # the caller retries instead of silently accepting a partial result.
            raise SandboxError(
                _unexpected_exit_message(proc, err_path), kind="resource_limit"
            )
    finally:
        if proc is not None and proc.poll() is None:
            kill_tree(proc.pid, job_object)
            try:
                proc.wait(timeout=10)
            except Exception:
                pass
        if job_object is not None:
            job_object.close()
        if proc is not None and proc.stdout is not None:
            try:
                proc.stdout.close()
            except Exception:
                pass
        if proc is not None and proc.stdin is not None:
            try:
                proc.stdin.close()
            except Exception:
                pass
        err_handle.close()
        _cleanup(workdir)


def _unexpected_exit_message(proc, err_path):
    code = proc.poll() if proc is not None else None
    tail = _read_tail(err_path)
    message = (
        f"The sandbox process exited unexpectedly (exit code {code}) without "
        "finishing. It was likely killed by a resource limit (memory / CPU / "
        "file size) or crashed."
    )
    if tail:
        message = f"{message}\n--- sandbox stderr (tail) ---\n{tail}"
    return message


def _timeout_message(cfg, err_path):
    tail = _read_tail(err_path)
    message = (
        f"Code execution exceeded the {cfg['timeout']:g}s sandbox time limit and "
        "the process was terminated."
    )
    if tail:
        message = f"{message}\n--- sandbox stderr (tail) ---\n{tail}"
    return message
