import os
import threading

from openai import OpenAI
from utils.get_config import config_data
from .get_api import get_api_key_from_file

# 默认 key 文件名：模型未配置 key_file 时使用该文件
DEFAULT_KEY_FILE = "api_key_openai.txt"
# key 文件所在目录（相对项目根目录）
KEY_FILE_DIR = os.path.join("agent", "utils", "llm_access")


def _build_model_configs():
    models = config_data.get("llm_models") or []
    built = []
    for i, m in enumerate(models):
        built.append({
            "id": str(m.get("id") or m.get("name") or f"model_{i}"),
            "name": m.get("name") or m.get("model") or f"Model {i + 1}",
            "model": m.get("model") or "",
            "url": m.get("url") or "",
            "key_file": m.get("key_file") or DEFAULT_KEY_FILE,
            "extra_params": m.get("extra_params") or {},
        })
    return built


MODEL_CONFIGS = _build_model_configs()

_lock = threading.Lock()
_current_model_id = MODEL_CONFIGS[0]["id"] if MODEL_CONFIGS else None
_clients = {}


def list_model_configs():
    """供前端展示的模型列表（不暴露 key 文件等敏感信息）"""
    return [
        {"id": m["id"], "name": m["name"], "model": m["model"], "url": m["url"]}
        for m in MODEL_CONFIGS
    ]


def get_model_config(model_id=None):
    """获取指定 id（默认当前）模型的完整配置；未指定或指定第一个模型时返回默认（第一个）模型"""
    if model_id is None:
        target = _current_model_id
    else:
        target = str(model_id)
        if target == "":
            target = MODEL_CONFIGS[0]["id"] if MODEL_CONFIGS else None
    for m in MODEL_CONFIGS:
        if m["id"] == target:
            return m
    return None


def get_current_model_id():
    return _current_model_id


def set_current_model(model_id):
    """切换当前使用的模型，返回新配置；无效 id 返回 None"""
    cfg = get_model_config(model_id)
    if cfg is None:
        return None
    with _lock:
        global _current_model_id
        _current_model_id = cfg["id"]
        _clients.pop(cfg["id"], None)
    return cfg


def _get_client(model_id=None):
    cfg = get_model_config(model_id)
    if cfg is None:
        raise ValueError("No LLM model configured")
    client = _clients.get(cfg["id"])
    if client is None:
        key_path = os.path.join(KEY_FILE_DIR, cfg["key_file"])
        client = OpenAI(api_key=get_api_key_from_file(key_path), base_url=cfg["url"])
        _clients[cfg["id"]] = client
    return client


def get_llm(model_id=None):
    """返回指定（默认当前）模型的 OpenAI client"""
    return _get_client(model_id)


class DynamicLLM:
    """代理对象：始终委托给当前选中模型的 OpenAI client，实现运行时无缝切换模型"""

    def __init__(self):
        self._llm_client = None
        self._llm_client_id = None

    def _resolve(self):
        cfg = get_model_config()
        cid = cfg["id"]
        if self._llm_client is None or self._llm_client_id != cid:
            self._llm_client = _get_client(cid)
            self._llm_client_id = cid
        return self._llm_client

    def __getattr__(self, name):
        if name.startswith("_llm_"):
            raise AttributeError(name)
        return getattr(self._resolve(), name)


def get_llm_dynamic():
    """返回可动态切换模型的 llm 代理，替代各处固定的 get_llm()"""
    return DynamicLLM()
