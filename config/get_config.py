import os

import yaml

# Resolve the config file relative to this file so the server can be started
# from any working directory (previously a './config/config.yaml' path that
# depended on the current working directory).
#
# ``CODE_EXEC_CONFIG`` is the single deliberate exception to "no environment
# variables": the main process writes a per-run config (a copy of this one whose
# database URLs are replaced by the read-only account) to a temp file and passes
# its path here when spawning the sandbox subprocess, so the child's in-memory
# database identity is read-only and the privileged password never reaches it.
# It has no effect on the main server process unless explicitly set.
_CONFIG_PATH = os.environ.get("CODE_EXEC_CONFIG") or os.path.join(
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
