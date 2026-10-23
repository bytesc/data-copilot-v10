import contextlib
import contextvars
import csv
import functools
import os
import threading
import time
from datetime import datetime

from utils.get_config import config_data

ENABLED = config_data.get("enable_perf_log", False)

PERF_LOG_PATH = os.environ.get("PERF_LOG_PATH", "perf_log.csv")
FIELDS = [
    "time",
    "api_name",
    "total_response_time",
    "llm_first_chunk_time",
    "llm_complete_time",
    "code_exec_time",
    "llm_input_chars",
]

_lock = threading.Lock()
_current = contextvars.ContextVar("perf_state", default=None)
_warned = False


class _PerfState:
    __slots__ = ("name", "start_wall", "start_mono", "first_chunk", "llm_done", "code_exec_ms", "llm_input_chars")

    def __init__(self, name):
        self.name = name
        self.start_wall = datetime.now()
        self.start_mono = time.monotonic()
        self.first_chunk = None
        self.llm_done = None
        self.code_exec_ms = 0.0
        self.llm_input_chars = 0


def _ensure_header():
    if os.path.exists(PERF_LOG_PATH):
        return
    with _lock:
        if os.path.exists(PERF_LOG_PATH):
            return
        with open(PERF_LOG_PATH, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writeheader()


def _write_row(state):
    row = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        "api_name": state.name,
        "total_response_time": round((time.monotonic() - state.start_mono) * 1000, 1),
        "llm_first_chunk_time": round((state.first_chunk - state.start_mono) * 1000, 1) if state.first_chunk else "",
        "llm_complete_time": round((state.llm_done - state.start_mono) * 1000, 1) if state.llm_done else "",
        "code_exec_time": round(state.code_exec_ms, 1) if state.code_exec_ms else "",
        "llm_input_chars": state.llm_input_chars if state.llm_input_chars else "",
    }
    try:
        _ensure_header()
        with _lock:
            with open(PERF_LOG_PATH, "a", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=FIELDS).writerow(row)
    except OSError as e:
        print(f"[perf_log] WARNING: failed to write row to {PERF_LOG_PATH}: {e} "
              f"(row skipped: {row.get('api_name')} @ {row.get('time')})")


def record_first_chunk():
    if not ENABLED:
        return
    st = _current.get()
    if st is not None and st.first_chunk is None:
        st.first_chunk = time.monotonic()


def record_llm_complete():
    if not ENABLED:
        return
    st = _current.get()
    if st is not None:
        st.llm_done = time.monotonic()


def record_code_exec(seconds):
    if not ENABLED:
        return
    st = _current.get()
    if st is not None:
        st.code_exec_ms += seconds * 1000


def record_llm_input(chars):
    if not ENABLED:
        return
    st = _current.get()
    if st is not None:
        st.llm_input_chars += chars


def perf_api(name):
    if not ENABLED:
        return lambda fn: fn

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            api_name = name(args, kwargs) if callable(name) else name
            state = _PerfState(api_name)
            it = fn(*args, **kwargs)
            try:
                while True:
                    _current.set(state)
                    try:
                        item = next(it)
                    except StopIteration:
                        break
                    yield item
            finally:
                _write_row(state)
        return wrapper
    return deco


@contextlib.contextmanager
def perf_context(name):
    if not ENABLED:
        yield
        return
    state = _PerfState(name)
    token = _current.set(state)
    try:
        yield
    finally:
        _write_row(state)
        _current.reset(token)
