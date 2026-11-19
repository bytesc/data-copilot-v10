"""token_proxy - a small OpenAI-compatible forwarding proxy.

Purpose
-------
Expose OpenAI-style endpoints under ``/v1/*`` from this machine, and forward
each request to a real upstream provider while injecting the real API token.
Callers (e.g. the main system) only ever see the proxy's own key, so the real
token stays hidden.

Run
---
    cd token_proxy
    python proxy.py

Two YAML config files live in this folder:
  * targets.yaml - a list of forwarding targets: name, url, key_file. It also
                   defines keys_dir, the folder holding the real-token files.
  * config.yaml  - server settings plus a list of exposed proxy keys; each proxy
                   key carries its own allowed target names, IP whitelist, and
                   model whitelist.

Real tokens are NOT written in either config file. Following the main project's
convention (agent/utils/llm_access/*.txt + get_api_key_from_file), each real
token lives in its own plain text file under the gitignored ``keys/`` folder and
is referenced by file name in targets.yaml.

Both streaming (``"stream": true``, Server-Sent Events) and non-streaming
responses are relayed byte-for-byte, including the upstream status and headers.
"""

from __future__ import annotations

import argparse
import ipaddress
import itertools
import json
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.yaml"
DEFAULT_TARGETS_PATH = BASE_DIR / "targets.yaml"

log = logging.getLogger("token_proxy")

# Hop-by-hop headers are connection specific and must not be forwarded.
HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)

# Request headers we drop before forwarding upstream: hop-by-hop plus anything
# the proxy must own (host, length, the caller's auth, and forwarding metadata).
DROP_REQUEST_HEADERS = HOP_BY_HOP | {
    "host",
    "content-length",
    "authorization",
    "api-key",
    "x-api-key",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-forwarded-port",
}

# Response headers we drop when relaying upstream back to the caller. Body length
# and transfer framing are re-derived by the server because we stream the body.
DROP_RESPONSE_HEADERS = HOP_BY_HOP | {"content-length"}

API_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


# --------------------------------------------------------------------------- #
# config model
# --------------------------------------------------------------------------- #
class Target:
    """A single real upstream: base URL + real token (from a key file)."""

    def __init__(
        self,
        name: str,
        base_url: str,
        token: str,
        auth_header: str = "Authorization",
        auth_scheme: str = "Bearer",
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.auth_header = auth_header
        self.auth_scheme = auth_scheme

    @property
    def auth_value(self) -> str:
        return f"{self.auth_scheme} {self.token}".strip()

    def upstream_url(self, rest_path: str, query: str) -> str:
        """Join the provider base with the request path (with the /v1 stripped)."""
        rest_path = rest_path.lstrip("/")
        url = f"{self.base_url}/{rest_path}" if rest_path else self.base_url
        return f"{url}?{query}" if query else url

    def describe(self) -> str:
        masked = "***" if len(self.token) <= 8 else f"{self.token[:4]}...{self.token[-4:]}"
        return f"{self.name} -> {self.base_url} (token {masked})"


class Policy:
    """What one exposed proxy key is allowed to do."""

    def __init__(
        self,
        key: str | None,
        target_names: list[str] | None,
        nets: list,
        models: set[str],
    ) -> None:
        self.key = key
        # None -> any target enabled in targets.yaml.
        self.target_names = target_names
        # empty -> any client IP.
        self.nets = nets
        # empty -> any model name.
        self.models = models


# Used when config.yaml declares no proxy keys at all (open proxy).
_OPEN_POLICY = Policy(key=None, target_names=None, nets=[], models=set())


# --------------------------------------------------------------------------- #
# config loading
# --------------------------------------------------------------------------- #
def get_api_key_from_file(file_path: Path) -> str:
    """Read a real API key from a text file (same convention as the main project)."""
    with file_path.open("r", encoding="utf-8") as handle:
        return handle.read().strip()


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _parse_networks(entries: list | None) -> list:
    networks = []
    for entry in entries or []:
        text = str(entry).strip()
        if not text:
            continue
        try:
            networks.append(ipaddress.ip_network(text, strict=False))
        except ValueError:
            log.warning("config: ignoring invalid ip_whitelist entry %r", entry)
    return networks


def build_targets(entries: list | None, keys_dir: Path) -> list[Target]:
    """Build targets from targets.yaml ``targets``.

    Each entry is a mapping with: name, url (real upstream base URL) and key_file
    (a plain text file holding the real token, resolved against ``keys_dir`` when
    not absolute).
    """
    targets: list[Target] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            log.warning("targets.yaml: ignoring invalid target entry %r", entry)
            continue
        name = entry.get("name")
        base_url = entry.get("url") or entry.get("base_url")
        key_file = entry.get("key_file")
        if not name or not base_url or not key_file:
            log.warning("targets.yaml: target entry needs name, url, key_file: %r", entry)
            continue
        key_path = Path(str(key_file))
        if not key_path.is_absolute():
            key_path = keys_dir / str(key_file)
        try:
            token = get_api_key_from_file(key_path)
        except OSError as exc:
            log.error("targets.yaml: target '%s' cannot read key file %s: %s", name, key_path, exc)
            continue
        if not token:
            log.error("targets.yaml: target '%s' key file %s is empty", name, key_path)
            continue
        targets.append(Target(name=str(name), base_url=str(base_url), token=token))
    return targets


def build_policies(entries: list | None) -> list[Policy]:
    """Build the per-proxy-key policies from config.yaml ``keys``.

    Each entry is a mapping with:
      key            - the expose proxy key clients must present.
      targets        - list of target names from targets.yaml this key may use.
      ip_whitelist   - allowed client IPs/CIDRs for this key (empty -> any).
      model_whitelist- allowed model names for this key (empty -> any).
    """
    policies: list[Policy] = []
    for entry in entries or []:
        if isinstance(entry, str):
            entry = {"key": entry}
        if not isinstance(entry, dict):
            log.warning("config: ignoring invalid keys entry %r", entry)
            continue
        key = entry.get("key") or entry.get("api_key")
        if not key:
            log.warning("config: keys entry needs a 'key': %r", entry)
            continue
        target_names = entry.get("targets")
        if target_names is not None:
            target_names = [str(name) for name in target_names]
        models = {str(m) for m in (entry.get("model_whitelist") or []) if str(m).strip()}
        policies.append(
            Policy(
                key=str(key),
                target_names=target_names,
                nets=_parse_networks(entry.get("ip_whitelist")),
                models=models,
            )
        )
    return policies


class ProxyState:
    """Everything the proxy needs at request time, derived from the two configs."""

    def __init__(self, config: dict, targets: list[Target], config_path: Path) -> None:
        self.config_path = config_path
        server = config.get("server") or {}
        self.host = str(server.get("host", "0.0.0.0"))
        self.port = int(server.get("port", 8080))

        self.strategy = str(config.get("strategy", "round_robin")).lower()
        self.timeout = float(config.get("timeout", 600) or 600)
        self.trust_proxy = bool(config.get("trust_proxy", False))

        self.targets = targets
        self.keys = build_policies(config.get("keys"))
        self._counter = itertools.count()
        self.client: httpx.AsyncClient | None = None

    # -- per-key access -----------------------------------------------------
    def authenticate(self, request: Request):
        """Return (policy, error_response)."""
        if not self.keys:
            return _OPEN_POLICY, None
        token = extract_token(request)
        if token:
            for policy in self.keys:
                if secrets.compare_digest(token, policy.key):
                    return policy, None
        return None, openai_error(
            401, "Invalid API key", code="invalid_api_key", err_type="authentication_error"
        )

    def allowed_targets(self, policy: Policy) -> list[Target]:
        if policy.target_names is None:
            return list(self.targets)
        wanted = set(policy.target_names)
        return [target for target in self.targets if target.name in wanted]

    def select_targets(self, allowed: list[Target], forced: str | None):
        """Return (ordered_candidates, error_response). Candidates are tried in order."""
        if not allowed:
            return None, openai_error(
                403,
                "No forwarding target is available for this API key",
                code="no_target",
                err_type="permission_error",
            )
        if forced:
            for target in allowed:
                if target.name == forced:
                    return [target], None
            return None, openai_error(
                400, f"Target '{forced}' is not allowed", code="target_not_allowed", err_type="permission_error"
            )
        if self.strategy == "first":
            return list(allowed), None
        start = next(self._counter) % len(allowed)
        return allowed[start:] + allowed[:start], None


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def openai_error(
    status: int, message: str, *, code: str | None = None, err_type: str = "invalid_request_error"
) -> JSONResponse:
    """An error body shaped like the OpenAI API error object."""
    return JSONResponse(
        {"error": {"message": message, "type": err_type, "code": code, "param": None}},
        status_code=status,
    )


def get_client_ip(request: Request, trust_proxy: bool) -> str:
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def ip_allowed(ip: str, networks: list) -> bool:
    if not networks:
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in network for network in networks)


def extract_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    if auth:
        return auth.strip()
    return (request.headers.get("api-key") or request.headers.get("x-api-key") or "").strip()


def extract_model(body: bytes, content_type: str) -> str | None:
    if not body or "json" not in content_type.lower():
        return None
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    model = data.get("model") if isinstance(data, dict) else None
    return model if isinstance(model, str) and model else None


def build_forward_headers(request: Request, target: Target) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in request.headers.items():
        lower = key.lower()
        if lower in DROP_REQUEST_HEADERS or lower.startswith("x-proxy-"):
            continue
        headers[key] = value
    headers[target.auth_header] = target.auth_value
    return headers


# --------------------------------------------------------------------------- #
# app
# --------------------------------------------------------------------------- #
def create_app(config_path: Path = DEFAULT_CONFIG_PATH, targets_path: Path = DEFAULT_TARGETS_PATH) -> FastAPI:
    config = load_config(config_path)
    targets_config = load_config(targets_path)

    keys_dir = Path(str(targets_config.get("keys_dir") or "keys"))
    if not keys_dir.is_absolute():
        keys_dir = (targets_path.parent / keys_dir).resolve()
    targets = build_targets(targets_config.get("targets"), keys_dir)

    state = ProxyState(config, targets, config_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state.client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=15.0, read=state.timeout, write=state.timeout, pool=state.timeout),
            follow_redirects=False,
        )
        log.info("listening on %s:%d", state.host, state.port)
        if state.targets:
            for target in state.targets:
                log.info("target enabled: %s", target.describe())
        else:
            log.warning("no forwarding target enabled - check targets.yaml and keys_dir")
        log.info("%d proxy key(s) configured", len(state.keys))
        try:
            yield
        finally:
            if state.client is not None:
                await state.client.aclose()

    app = FastAPI(title="token_proxy", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.proxy = state
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def root():
        return {"service": "token_proxy", "targets": [t.name for t in state.targets], "keys": len(state.keys)}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    async def handle(rest_path: str, request: Request):
        st: ProxyState = request.app.state.proxy
        client = st.client

        policy, error = st.authenticate(request)
        if error is not None:
            log.warning("denied (key) path=%s", request.url.path)
            return error

        ip = get_client_ip(request, st.trust_proxy)
        if not ip_allowed(ip, policy.nets):
            log.warning("denied (ip) ip=%s path=%s", ip, request.url.path)
            return openai_error(
                403, f"IP {ip} is not allowed", code="ip_not_allowed", err_type="permission_error"
            )

        body = await request.body()
        model = extract_model(body, request.headers.get("content-type", ""))
        if model is not None and policy.models and model not in policy.models:
            log.warning("denied (model) ip=%s model=%s", ip, model)
            return openai_error(
                403, f"Model '{model}' is not allowed", code="model_not_allowed", err_type="permission_error"
            )

        forced = request.headers.get("x-proxy-target")
        candidates, error = st.select_targets(st.allowed_targets(policy), forced)
        if error is not None:
            return error

        query = request.url.query
        last_error: Exception | None = None
        for target in candidates:
            url = target.upstream_url(rest_path, query)
            headers = build_forward_headers(request, target)
            upstream_request = client.build_request(
                request.method, url, headers=headers, content=body if body else None
            )
            try:
                response = await client.send(upstream_request, stream=True)
            except httpx.TransportError as exc:
                # No response was received yet, so it is safe to fail over.
                log.warning("target '%s' unreachable (%s), trying next", target.name, exc)
                last_error = exc
                continue

            log.info(
                "%s /v1/%s ip=%s target=%s status=%s",
                request.method,
                rest_path,
                ip,
                target.name,
                response.status_code,
            )
            relay_headers = {
                key: value
                for key, value in response.headers.items()
                if key.lower() not in DROP_RESPONSE_HEADERS
            }
            return StreamingResponse(
                response.aiter_raw(),
                status_code=response.status_code,
                headers=relay_headers,
                background=BackgroundTask(response.aclose),
            )

        return openai_error(
            502,
            f"All upstream targets failed: {last_error}",
            code="upstream_unavailable",
            err_type="api_error",
        )

    @app.api_route("/v1/{rest_path:path}", methods=API_METHODS, include_in_schema=False)
    async def proxy_v1(rest_path: str, request: Request):
        return await handle(rest_path, request)

    @app.api_route("/v1", methods=API_METHODS, include_in_schema=False)
    async def proxy_v1_root(request: Request):
        return await handle("", request)

    return app


app = create_app()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenAI-compatible forwarding proxy")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="path to config.yaml (proxy keys)")
    parser.add_argument(
        "--targets", type=Path, default=DEFAULT_TARGETS_PATH, help="path to targets.yaml (real upstreams)"
    )
    parser.add_argument("--host", default=None, help="override server.host")
    parser.add_argument("--port", type=int, default=None, help="override server.port")
    parser.add_argument("--log-level", default="info", help="uvicorn log level")
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = parse_args()
    application = create_app(args.config, args.targets)
    server_state: ProxyState = application.state.proxy
    uvicorn.run(
        application,
        host=args.host or server_state.host,
        port=args.port or server_state.port,
        log_level=args.log_level,
    )
