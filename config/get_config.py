import os

import yaml

# Resolve the config file relative to this file so the server can be started
# from any working directory (previously a './config/config.yaml' path that
# depended on the current working directory).
_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "config.yaml",
)


def load_config(path=_CONFIG_PATH):
    with open(path, "r", encoding="utf-8") as stream:
        try:
            return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise RuntimeError(f"Failed to parse config file '{path}': {exc}") from exc


# Optional environment overrides for deployment (for example Docker Compose):
# a set environment variable wins over config.yaml, so a running image can be
# re-pointed (static file URL, database URLs, bind address) without rebuilding.
_ENV_OVERRIDES = {
    "STATIC_PATH": "static_path",
    "SERVER_HOST": "server_host",
    "SERVER_PORT": "server_port",
    "MYSQL_URL": "mysql",
    "MYSQL_READONLY_URL": "mysql_readonly",
    "MYSQL_SYS_URL": "mysql_sys",
}


def _apply_env_overrides(cfg):
    cfg = cfg or {}
    for env_key, cfg_key in _ENV_OVERRIDES.items():
        value = os.getenv(env_key)
        if value:
            cfg[cfg_key] = int(value) if cfg_key == "server_port" else value
    return cfg


# Single source of truth for the whole project. Other modules re-export this
# object instead of re-reading the file, and it is never printed so credentials
# (e.g. the database password) do not leak into logs.
config_data = _apply_env_overrides(load_config())
