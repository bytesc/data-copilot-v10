import json
import os
import yaml
import threading
import urllib.request
import subprocess
import sys
from urllib.parse import urlparse
from typing import Optional


# Resolve the config path relative to this file so the server can be started
# from any working directory. The previous CWD-relative path made a valid
# config look "missing" when the process was launched elsewhere.
MCP_SERVERS_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "config",
    "mcp_servers.yaml",
)

_mcp_servers_cache = None


class MCPError(Exception):
    pass


class MCPConnectionError(MCPError):
    pass


class MCPToolError(MCPError):
    pass


def load_mcp_servers() -> list[dict]:
    global _mcp_servers_cache
    if _mcp_servers_cache is not None:
        return _mcp_servers_cache
    try:
        with open(MCP_SERVERS_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        # MCP is optional: a missing config simply means no servers are set up.
        # Do not raise, otherwise an optional feature blocks startup.
        print(f"[WARNING] MCP servers config not found at {MCP_SERVERS_CONFIG_PATH}; MCP disabled")
        _mcp_servers_cache = []
        return _mcp_servers_cache
    except Exception as e:
        raise MCPError(f"Failed to load MCP servers config: {e}")
    _mcp_servers_cache = data.get("mcp_servers", []) if data else []
    return _mcp_servers_cache


def get_mcp_server(name: str) -> Optional[dict]:
    servers = load_mcp_servers()
    for s in servers:
        if s.get("name") == name:
            return s
    return None


class MCPClient:
    def __init__(self, server_config: dict):
        self.name = server_config.get("name", "")
        self.description = server_config.get("description", "")
        self.transport = server_config.get("transport", "stdio")
        self.url = server_config.get("url", "")
        self.command = server_config.get("command", "")
        self.args = server_config.get("args", [])
        self._message_endpoint: Optional[str] = None
        self._request_id = 0
        self._responses: dict[int, dict] = {}
        # One Event per in-flight request id. A single shared Event would let a
        # response for a *different* request wake the wrong waiter, and a late
        # response (after a timeout) could be misread as the current reply.
        self._events: dict[int, threading.Event] = {}
        self._closed = False
        self._lock = threading.Lock()

        # SSE transport resources
        self._sse_resp = None
        self._read_thread: Optional[threading.Thread] = None

        # stdio transport resources
        self._process: Optional[subprocess.Popen] = None
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def connect(self):
        if self.transport == "sse":
            self._connect_sse()
        elif self.transport == "stdio":
            self._connect_stdio()
        else:
            raise MCPError(f"Unsupported transport: {self.transport}. Supported: 'sse', 'stdio'")

    # ── SSE transport ────────────────────────────────────────────────

    def _connect_sse(self):
        if not self.url:
            raise MCPConnectionError(f"MCP server '{self.name}' has no URL configured for sse transport.")
        try:
            req = urllib.request.Request(self.url, headers={"Accept": "text/event-stream"})
            self._sse_resp = urllib.request.urlopen(req, timeout=30)

            event_type = None
            event_data = ""
            while True:
                line_bytes = self._sse_resp.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").strip("\r\n")
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    event_data = line[6:]
                elif line == "" and event_type is not None:
                    if event_type == "endpoint":
                        self._message_endpoint = event_data.strip()
                        break
                    event_type = None
                    event_data = ""

            if not self._message_endpoint:
                raise MCPConnectionError(f"Failed to get endpoint from SSE stream for server '{self.name}'")

            if self._message_endpoint.startswith("/"):
                parsed = urlparse(self.url)
                base = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
                self._message_endpoint = base + self._message_endpoint

            self._read_thread = threading.Thread(target=self._read_sse_loop, args=(self._sse_resp,), daemon=True)
            self._read_thread.start()

            self._send_initialize()
        except Exception as e:
            self.close()
            if isinstance(e, MCPError):
                raise
            raise MCPConnectionError(f"Failed to connect to SSE MCP server '{self.name}': {e}")

    def _read_sse_loop(self, resp):
        try:
            event_type = None
            event_data = ""
            while not self._closed:
                line_bytes = resp.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").strip("\r\n")
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    event_data = line[6:]
                elif line == "" and event_type is not None and event_data:
                    if event_type == "message":
                        try:
                            msg = json.loads(event_data)
                            if "id" in msg:
                                self._store_response(msg)
                        except json.JSONDecodeError:
                            pass
                    event_type = None
                    event_data = ""
        except Exception:
            pass

    def _send_via_sse(self, data: bytes) -> bytes:
        req = urllib.request.Request(
            self._message_endpoint, data=data,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=30)
        body = resp.read()
        resp.close()
        return body

    # ── stdio transport ──────────────────────────────────────────────

    def _connect_stdio(self):
        if not self.command:
            raise MCPConnectionError(f"MCP server '{self.name}' has no command configured for stdio transport.")
        try:
            self._process = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self._stdout_thread = threading.Thread(target=self._read_stdio_loop, daemon=True)
            self._stdout_thread.start()
            self._stderr_thread = threading.Thread(target=self._read_stderr_loop, daemon=True)
            self._stderr_thread.start()

            self._send_initialize()
        except Exception as e:
            self.close()
            if isinstance(e, MCPError):
                raise
            raise MCPConnectionError(f"Failed to connect to stdio MCP server '{self.name}': {e}")

    def _read_stdio_loop(self):
        try:
            while not self._closed and self._process and self._process.stdout:
                line = self._process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    if "id" in msg:
                        self._store_response(msg)
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

    def _read_stderr_loop(self):
        """Drain stderr so a chatty stdio server cannot block on a full pipe.

        ``stderr=subprocess.PIPE`` with no reader is a classic deadlock: once the
        OS pipe buffer fills, the child blocks on its next write and stops
        serving requests (every call then times out). Reading stderr here keeps
        the child unblocked.
        """
        try:
            while not self._closed and self._process and self._process.stderr:
                line = self._process.stderr.readline()
                if not line:
                    break
                line = line.rstrip()
                if line:
                    print(f"[MCP {self.name} stderr] {line}")
        except Exception:
            pass

    def _send_via_stdio(self, data: bytes) -> bytes:
        self._process.stdin.write(data.decode("utf-8") if isinstance(data, bytes) else data)
        self._process.stdin.write("\n")
        self._process.stdin.flush()
        return b""

    # ── shared JSON-RPC logic ────────────────────────────────────────

    def _store_response(self, msg: dict):
        """Record a JSON-RPC response and wake only its own waiter."""
        req_id = msg.get("id")
        if req_id is None:
            return
        with self._lock:
            self._responses[req_id] = msg
            event = self._events.get(req_id)
        if event is not None:
            event.set()

    def _send_initialize(self):
        result = self._dispatch_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "data-copilot", "version": "1.0"}
        })
        if "error" in result:
            raise MCPConnectionError(f"Initialize failed: {result['error']}")
        self._dispatch_notification("notifications/initialized", {})

    def _dispatch_request(self, method: str, params: dict = None) -> dict:
        req_id = self._next_id()
        body = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            body["params"] = params

        # Register this request's own event before sending, so a response that
        # arrives for a different id can never satisfy this waiter.
        event = threading.Event()
        with self._lock:
            self._events[req_id] = event

        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        try:
            if self.transport == "sse":
                self._send_via_sse(data)
            elif self.transport == "stdio":
                self._send_via_stdio(data)
        except Exception as e:
            with self._lock:
                self._events.pop(req_id, None)
                self._responses.pop(req_id, None)
            raise MCPConnectionError(f"Failed to send request '{method}': {e}")

        if not event.wait(timeout=30):
            # Drop any late/partial state for this id so it cannot linger.
            with self._lock:
                self._events.pop(req_id, None)
                self._responses.pop(req_id, None)
            raise MCPConnectionError(f"Timeout waiting for response to '{method}'")

        with self._lock:
            self._events.pop(req_id, None)
            response = self._responses.pop(req_id, {})

        if self._closed and not response:
            raise MCPConnectionError(f"Connection closed while waiting for '{method}'")
        return response

    def _dispatch_notification(self, method: str, params: dict = None):
        body = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        try:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            if self.transport == "sse":
                self._send_via_sse(data)
            elif self.transport == "stdio":
                self._send_via_stdio(data)
        except Exception:
            pass

    # ── public API ───────────────────────────────────────────────────

    def list_tools(self) -> list[dict]:
        result = self._dispatch_request("tools/list", {})
        if "error" in result:
            raise MCPToolError(f"tools/list failed: {result['error']}")
        return result.get("result", {}).get("tools", [])

    def call_tool(self, tool_name: str, arguments: dict = None) -> dict:
        params = {"name": tool_name}
        if arguments is not None:
            params["arguments"] = arguments
        result = self._dispatch_request("tools/call", params)
        if "error" in result:
            raise MCPToolError(f"tools/call '{tool_name}' failed: {result['error']}")
        return result.get("result", {})

    def close(self):
        self._closed = True
        # Wake every in-flight waiter so none blocks the full timeout once the
        # transport goes away.
        with self._lock:
            pending = list(self._events.values())
        for event in pending:
            event.set()
        if self._sse_resp is not None:
            try:
                self._sse_resp.close()
            except Exception:
                pass
            self._sse_resp = None
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
            self._process = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()