"""Cross-platform resource limits and process-tree termination (sandbox layer 4).

All platform differences live here and are applied by capability probing: if the
current platform does not support a limit, it is skipped (with a warning) instead
of crashing. The main flow stays platform-agnostic.

Two roles are provided:

* :func:`set_process_limits` / :func:`start_orphan_watchdog` run *inside* the
  sandbox child process.
* :class:`WindowsJob` / :func:`kill_tree` run *in* the parent process to terminate
  the whole child tree (including any MCP stdio grandchildren) on timeout.
"""

import ctypes
import os
import signal
import subprocess
import threading
import time

try:  # POSIX only
    import resource
except ImportError:  # pragma: no cover - Windows
    resource = None

IS_WINDOWS = os.name == "nt"

_warned = set()


def _warn(message):
    if message in _warned:
        return
    _warned.add(message)
    print(f"[sandbox.limits] WARNING: {message}", flush=True)


# --------------------------------------------------------------------------- #
# Child side: POSIX rlimits (best effort)
# --------------------------------------------------------------------------- #
def _apply_rlimit(kind, value):
    try:
        soft, hard = resource.getrlimit(kind)
        if hard != resource.RLIM_INFINITY:
            value = min(value, hard)
        resource.setrlimit(kind, (value, hard))
    except (ValueError, OSError) as exc:
        _warn(f"could not set rlimit {kind}: {exc}")


def set_process_limits(max_memory_mb=None, cpu_seconds=None,
                       max_processes=None, max_file_mb=None):
    """Apply POSIX resource limits in the current (child) process.

    Every limit is applied independently; unsupported limits degrade silently.
    """
    if resource is None:
        return
    if max_memory_mb:
        _apply_rlimit(resource.RLIMIT_AS, int(max_memory_mb) * 1024 * 1024)
    if cpu_seconds:
        _apply_rlimit(resource.RLIMIT_CPU, int(cpu_seconds))
    if max_processes:
        _apply_rlimit(resource.RLIMIT_NPROC, int(max_processes))
    if max_file_mb:
        _apply_rlimit(resource.RLIMIT_FSIZE, int(max_file_mb) * 1024 * 1024)


# --------------------------------------------------------------------------- #
# Parent side: Windows Job Object (memory cap + kill-on-close + tree kill)
# --------------------------------------------------------------------------- #
if IS_WINDOWS:
    import ctypes.wintypes as _wintypes

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _PROCESS_TERMINATE = 0x0001
    _PROCESS_SET_QUOTA = 0x0100


class WindowsJob:
    """Windows Job Object wrapper: caps memory and kills the whole tree."""

    def __init__(self, max_memory_mb=None, kill_on_close=True):
        self.handle = None
        self._k32 = None
        if not IS_WINDOWS:
            return
        try:
            self._k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self.handle = self._k32.CreateJobObjectW(None, None)
            if not self.handle:
                raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
            info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            flags = 0
            if max_memory_mb:
                flags |= _JOB_OBJECT_LIMIT_PROCESS_MEMORY
                info.ProcessMemoryLimit = int(max_memory_mb) * 1024 * 1024
            if kill_on_close:
                flags |= _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            info.BasicLimitInformation.LimitFlags = flags
            ok = self._k32.SetInformationJobObject(
                self.handle,
                _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            if not ok:
                raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")
        except OSError as exc:
            _warn(f"job object unavailable ({exc}); falling back to taskkill")
            self.close()

    def assign(self, pid):
        if not self.handle:
            return False
        try:
            handle = self._k32.OpenProcess(
                _PROCESS_TERMINATE | _PROCESS_SET_QUOTA, False, pid)
            if not handle:
                return False
            try:
                return bool(self._k32.AssignProcessToJobObject(self.handle, handle))
            finally:
                self._k32.CloseHandle(handle)
        except OSError:
            return False

    def terminate(self):
        if self.handle:
            try:
                self._k32.TerminateJobObject(self.handle, 1)
            except OSError:
                pass

    def close(self):
        if self.handle:
            try:
                self._k32.CloseHandle(self.handle)
            except OSError:
                pass
        self.handle = None


def kill_tree(pid, job=None):
    """Kill a process tree: job object when available, else pgid / taskkill."""
    if job is not None:
        job.terminate()
        job.close()
        # Do not return here: if assigning the child to the job failed (e.g. the
        # parent already runs inside a job), the job is empty and we still need
        # the targeted fallback below to actually stop the child.
    if IS_WINDOWS:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except OSError:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# Child side: orphan protection (parent death -> self-terminate)
# --------------------------------------------------------------------------- #
def _parent_alive(pid):
    if pid <= 1:
        return False
    if IS_WINDOWS:
        try:
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = k32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
            if not handle:
                return False
            try:
                # WAIT_OBJECT_0 (0) means the process has exited.
                return k32.WaitForSingleObject(handle, 0) != 0
            finally:
                k32.CloseHandle(handle)
        except OSError:
            return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start_orphan_watchdog(interval=2.0):
    """Daemon thread that exits the child if the parent process disappears."""
    parent = os.getppid()

    def _loop():
        while True:
            time.sleep(interval)
            if not _parent_alive(parent):
                os._exit(1)

    thread = threading.Thread(target=_loop, name="sandbox-orphan-watchdog",
                              daemon=True)
    thread.start()
    return thread
