# Re-export the canonical config loaded by ``config.get_config`` so the whole
# project shares one config object (previously each package read its own copy).
from config.get_config import config_data, load_config  # noqa: F401
