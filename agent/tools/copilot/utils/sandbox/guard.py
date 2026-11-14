"""Runtime guards for the sandbox child process (pure Python, cross-platform).

Layer 6 of the sandbox: an in-process ``sys.addaudithook`` that enforces, at
*run time*, what the AST review (layer 1) cannot see — the file reads and
network connections performed deep inside whitelisted libraries such as
``pandas.read_csv`` / ``numpy.load`` / ``urllib``.

Two independent allow-lists are applied:

* **file access** — ``open`` / ``io.open_code`` are only allowed for approved
  paths (``tmp_imgs``, the project's Python source, stdlib / site-packages, the
  bundled ``assets`` dir, the matplotlib config dir, plus any extra dirs/files
  from ``sandbox.yaml``). Everything else — notably ``config/config.yaml`` and
  ``agent/utils/llm_access/*.txt`` — is denied. ``deny`` always wins.
* **network** — ``socket.connect`` / ``socket.getaddrinfo`` are only allowed for
  approved hosts (from ``sandbox.yaml`` plus the DB / LLM / MCP hosts the parent
  injects at run time). All other destinations are refused.

The hook is installed immediately before the generated code is ``exec``'d, so
import-time library reads (which happen earlier) are not affected. Once added,
an audit hook cannot be removed, which is why this is installed last.
"""

import fnmatch
import os
import socket
import sys


def _as_real(path):
    try:
        return os.path.realpath(str(path))
    except Exception:
        return ""


def _norm_host(host):
    return str(host or "").strip().lower().rstrip(".")


# Flags that mark an `open`/`os.open` as a WRITE (used to enforce read-only roots).
_WRITE_FLAGS = (
    getattr(os, "O_WRONLY", 0) | getattr(os, "O_RDWR", 0)
    | getattr(os, "O_CREAT", 0) | getattr(os, "O_APPEND", 0)
    | getattr(os, "O_TRUNC", 0)
)


def _is_write(mode, flags):
    """Best-effort: does this ``open`` intend to write?"""
    if isinstance(mode, str):
        return any(ch in mode for ch in ("w", "a", "x", "+"))
    if isinstance(flags, int):
        return bool(flags & _WRITE_FLAGS)
    return False


class _Guard:
    def __init__(self, cfg, project_root):
        self.project = _as_real(project_root)

        fa = (cfg or {}).get("file_access") or {}
        net = (cfg or {}).get("network") or {}

        # Everything the guard enforces comes from config/sandbox.yaml.
        self.code_exts = tuple(str(e).lower() for e in (fa.get("code_exts") or []))

        self.allow_write_dirs = [self._resolve(p) for p in (fa.get("allow_write_dirs") or [])]
        self.allow_read_dirs = [self._resolve(p) for p in (fa.get("allow_read_dirs") or [])]
        self.allow_read_files = {self._resolve(p) for p in (fa.get("allow_read_files") or [])}
        # deny_paths: plain paths (deny the path and everything under it) plus
        # glob patterns (e.g. "agent/utils/llm_access/*.txt").
        self.deny_paths = []
        self.deny_globs = []
        for _raw in (fa.get("deny_paths") or []):
            _text = str(_raw)
            if any(ch in _text for ch in "*?["):
                self.deny_globs.append(self._abs_pattern(_text))
            else:
                self.deny_paths.append(self._resolve(_text))

        # Interpreter-dependent roots: their actual paths cannot be written
        # statically (they depend on the running Python), so their use is decided
        # by config flags and the paths are derived here.
        self.lib_roots = []
        if fa.get("python_libs"):
            for p in (sys.prefix, sys.base_prefix, getattr(sys, "exec_prefix", "")):
                real = _as_real(p)
                if real and real not in self.lib_roots:
                    self.lib_roots.append(real)

        self.mpl_dir = ""
        if fa.get("matplotlib_cache"):
            try:
                import matplotlib
                self.mpl_dir = _as_real(matplotlib.get_configdir())
            except Exception:
                self.mpl_dir = ""

        # ---- network ----
        # "*" in allow_hosts means "allow EVERY host"; "*" in allow_ports means
        # "allow EVERY port". Values come from config/sandbox.yaml (no defaults).
        raw_hosts = [h for h in (net.get("allow_hosts") or []) if str(h).strip()]
        self.allow_any_host = any(str(h).strip() == "*" for h in raw_hosts)
        self.allow_hosts = {
            _norm_host(h) for h in raw_hosts if str(h).strip() != "*"
        }
        raw_ports = [p for p in (net.get("allow_ports") or []) if str(p).strip()]
        self.allow_any_port = any(str(p).strip() == "*" for p in raw_ports)
        self.allow_ports = set()
        for p in raw_ports:
            try:
                self.allow_ports.add(int(str(p).strip()))
            except ValueError:
                pass
        # Resolve allowed hostnames to IPs up front so a direct connection to a
        # raw IP of an approved host is permitted, while an arbitrary IP is not.
        self.allow_ips = set()
        for host in list(self.allow_hosts):
            self._resolve_host_ips(host)

    # -- path helpers -------------------------------------------------------
    def _resolve(self, p):
        text = str(p)
        if not os.path.isabs(text):
            text = os.path.join(self.project, text)
        return _as_real(text)

    def _under(self, real, root):
        return bool(root) and (real == root or real.startswith(root + os.sep))

    def _abs_pattern(self, pattern):
        """Absolute, '/'-separated glob pattern for deny matching."""
        text = pattern.replace("\\", "/")
        if not os.path.isabs(text):
            text = os.path.join(self.project, text).replace("\\", "/")
        return text

    def _denied(self, real):
        for d in self.deny_paths:
            if self._under(real, d):
                return True
        if self.deny_globs:
            norm = real.replace(os.sep, "/")
            for pattern in self.deny_globs:
                if fnmatch.fnmatch(norm, pattern):
                    return True
        return False

    # -- network helpers ----------------------------------------------------
    def _resolve_host_ips(self, host):
        try:
            for info in socket.getaddrinfo(host, None):
                self.allow_ips.add(str(info[4][0]))
        except OSError:
            pass

    def _host_ok(self, host):
        if self.allow_any_host:
            return True
        h = _norm_host(host)
        if not h:
            return False
        if h in self.allow_hosts:
            return True
        return any(h.endswith("." + d) for d in self.allow_hosts)

    def _port_ok(self, port):
        if not port:
            # None / 0 / "" = unknown port, do not gate.
            return True
        if self.allow_any_port:
            return True
        try:
            value = int(port)
        except (TypeError, ValueError):
            # Service name or other non-numeric port: do not gate.
            return True
        return value in self.allow_ports

    # -- policy -------------------------------------------------------------
    def file_ok(self, path, write=False):
        real = _as_real(path)
        if not real:
            # Non-path handles (e.g. an int fd) have nothing to check.
            return True
        if self._denied(real):
            return False
        # Read + write areas.
        for d in self.allow_write_dirs:
            if self._under(real, d):
                return True
        if self.mpl_dir and self._under(real, self.mpl_dir):
            return True
        # Read-only areas (writes are refused).
        if real in self.allow_read_files:
            return not write
        for d in self.allow_read_dirs:
            if self._under(real, d):
                return not write
        for root in self.lib_roots:
            if self._under(real, root):
                return not write
        # Project source code, so imports of the project's own modules work.
        if self._under(real, self.project) and real.lower().endswith(self.code_exts):
            return not write
        return False

    def install(self):
        def _hook(event, args):
            if event in ("open", "io.open_code"):
                path = args[0] if args else None
                mode = args[1] if len(args) > 1 else None
                flags = args[2] if len(args) > 2 else None
                if isinstance(path, (str, bytes, os.PathLike)) and not self.file_ok(
                    path, write=_is_write(mode, flags)
                ):
                    raise PermissionError(
                        f"sandbox: file access is not allowed: {path!r}"
                    )
                return
            if event == "socket.getaddrinfo":
                host = args[0] if args else None
                port = args[1] if len(args) > 1 else None
                if host and not (self._host_ok(host) or str(host) in self.allow_ips):
                    raise PermissionError(
                        f"sandbox: network access is not allowed (DNS {host!r})"
                    )
                if not self._port_ok(port):
                    raise PermissionError(
                        f"sandbox: network access is not allowed (port {port!r})"
                    )
            elif event == "socket.connect":
                addr = args[1] if len(args) > 1 else None
                if isinstance(addr, tuple) and addr:
                    target = str(addr[0])
                    port = addr[1] if len(addr) > 1 else None
                    if target not in self.allow_ips and not self._host_ok(target):
                        raise PermissionError(
                            f"sandbox: network access is not allowed ({addr!r})"
                        )
                    if not self._port_ok(port):
                        raise PermissionError(
                            f"sandbox: network access is not allowed (port {port!r})"
                        )
            elif event in ("socket.gethostbyname", "socket.gethostbyaddr"):
                host = args[0] if args else None
                if host and not (self._host_ok(host) or str(host) in self.allow_ips):
                    raise PermissionError(
                        f"sandbox: network access is not allowed ({host!r})"
                    )

        sys.addaudithook(_hook)


def install_guard(cfg, project_root):
    """Install the file-access and network guard in the current process."""
    _Guard(cfg, project_root).install()
