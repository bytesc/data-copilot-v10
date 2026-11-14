import os

import yaml

# Resolve the sandbox config relative to this file so the server can be started
# from any working directory (same convention as config/get_config.py).
#
# This is a SEPARATE file from config.yaml on purpose: it only holds settings
# for the LLM code-execution sandbox (resource limits, runtime file-access
# guard and network allow-list), so the sandbox can be tuned without touching
# the main server config.
#
# This module intentionally contains NO default values: every sandbox setting
# comes from config/sandbox.yaml, which is the single source of truth. A
# missing/omitted key is surfaced at use time rather than silently defaulted.
_SANDBOX_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "sandbox.yaml",
)


def load_sandbox_config(path=_SANDBOX_CONFIG_PATH):
    try:
        with open(path, "r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream) or {}
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as exc:
        raise RuntimeError(
            f"Failed to parse sandbox config file '{path}': {exc}"
        ) from exc
    if not isinstance(data, dict):
        return {}
    return data


sandbox_config_data = load_sandbox_config()


def get_section(name):
    """Return a raw sandbox config section (``{}`` when absent)."""
    section = sandbox_config_data.get(name)
    return section if isinstance(section, dict) else {}
