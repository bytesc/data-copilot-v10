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


# Single source of truth for the whole project: config/config.yaml only.
# Environment variables are deliberately NOT consulted, so a running instance is
# fully described by this file (edit it, then restart / rebuild the image).
# Other modules re-export this object instead of re-reading the file, and it is
# never printed so credentials (e.g. the database password) do not leak to logs.
config_data = load_config()
