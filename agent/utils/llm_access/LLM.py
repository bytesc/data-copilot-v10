import contextvars
import os
import threading

from openai import OpenAI
from utils.get_config import config_data
from .get_api import get_api_key_from_file

# 默认 key 文件名：模型未配置 key_file 时使用该文件
DEFAULT_KEY_FILE = "api_key_openai.txt"
# key 文件所在目录（相对项目根目录）
KEY_FILE_DIR = os.path.join("agent", "utils", "llm_access")


def _normalize_reasoning_effort(value):
    """把配置中的 reasoning_effort 统一成去重后的字符串列表。"""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    options = []
    for item in value:
        text = str(item).strip()
        if text and text not in options:
            options.append(text)
    return options


def _normalize_style_temperature(value):
    """把 {样式名: 温度} 字典标准化为按配置顺序排列的字典。"""
    if not isinstance(value, dict):
        return {}
    styles = {}
    for name, temp in value.items():
        label = str(name).strip()
        if not label:
            continue
        try:
            styles[label] = float(temp)
        except (TypeError, ValueError):
            continue
    return styles


def _normalize_bool(value):
    """把配置中的布尔开关标准化为 True/False。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


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
            "reasoning_effort": _normalize_reasoning_effort(m.get("reasoning_effort")),
            "style_temperature": _normalize_style_temperature(m.get("style_temperature")),
            "supports_images": _normalize_bool(m.get("supports_images", False)),
            "extra_params": m.get("extra_params") or {},
        })
    return built


MODEL_CONFIGS = _build_model_configs()

_lock = threading.Lock()
_DEFAULT_MODEL_ID = MODEL_CONFIGS[0]["id"] if MODEL_CONFIGS else None
_DEFAULT_REASONING_EFFORT = (
    MODEL_CONFIGS[0]["reasoning_effort"][0]
    if MODEL_CONFIGS and MODEL_CONFIGS[0]["reasoning_effort"]
    else ""
)

# 选择状态按请求隔离（来自前端每次请求携带的参数），后端不做持久化，
# 避免多个用户选择不同模型时互相覆盖。
_current_model_id_var = contextvars.ContextVar(
    "llm_current_model_id", default=_DEFAULT_MODEL_ID
)
_current_reasoning_effort_var = contextvars.ContextVar(
    "llm_current_reasoning_effort", default=_DEFAULT_REASONING_EFFORT
)
# Style 默认 Default（空字符串，不额外上传 temperature）
_current_style_var = contextvars.ContextVar("llm_current_style", default="")
# 是否随请求上传 blackboard 图片；None 表示按模型能力取默认值
_current_use_images_var = contextvars.ContextVar("llm_current_use_images", default=None)
_clients = {}


def _default_use_images(cfg):
    return bool(cfg and cfg.get("supports_images"))


def apply_request_selection(model_id=None, reasoning_effort=None, style=None, use_images=None):
    """按前端本次请求携带的值设置上下文，不写入全局共享状态。

    None 表示请求未携带该字段，此时使用模型默认值；空字符串表示 Default。
    """
    cfg = get_model_config(model_id) if model_id else None
    if cfg is None:
        cfg = MODEL_CONFIGS[0] if MODEL_CONFIGS else None
    if cfg is None:
        _current_model_id_var.set(None)
        _current_reasoning_effort_var.set("")
        _current_style_var.set("")
        _current_use_images_var.set(False)
        return
    _current_model_id_var.set(cfg["id"])

    if reasoning_effort is None:
        effort = _default_reasoning_effort(cfg)
    elif reasoning_effort == "" or reasoning_effort in cfg["reasoning_effort"]:
        effort = reasoning_effort
    else:
        effort = _default_reasoning_effort(cfg)
    _current_reasoning_effort_var.set(effort)

    if style is None or style == "" or style in cfg["style_temperature"]:
        current_style = style or ""
    else:
        current_style = ""
    _current_style_var.set(current_style)

    if use_images is None:
        use_images_value = _default_use_images(cfg)
    else:
        use_images_value = _normalize_bool(use_images) and cfg["supports_images"]
    _current_use_images_var.set(use_images_value)


def _default_reasoning_effort(cfg):
    options = cfg.get("reasoning_effort") or []
    return options[0] if options else ""


def _default_style(cfg):
    """Style 默认使用 Default（不上传 temperature）。"""
    return ""


def list_model_configs():
    """供前端展示的模型列表（不暴露 key 文件等敏感信息）"""
    current_id = get_current_model_id()
    current_effort = get_current_reasoning_effort()
    current_style = get_current_style()
    return [
        {
            "id": m["id"],
            "name": m["name"],
            "model": m["model"],
            "url": m["url"],
            "reasoning_effort_options": list(m["reasoning_effort"]),
            "reasoning_effort_selected": current_effort if m["id"] == current_id else "",
            "style_options": list(m["style_temperature"].keys()),
            "style_selected": current_style if m["id"] == current_id else "",
            "supports_images": bool(m["supports_images"]),
        }
        for m in MODEL_CONFIGS
    ]


def get_model_config(model_id=None):
    """获取指定 id（默认当前）模型的完整配置；未指定或指定第一个模型时返回默认（第一个）模型"""
    if model_id is None:
        target = get_current_model_id()
    else:
        target = str(model_id)
        if target == "":
            target = MODEL_CONFIGS[0]["id"] if MODEL_CONFIGS else None
    for m in MODEL_CONFIGS:
        if m["id"] == target:
            return m
    return None


def model_supports_images(model_id=None):
    """当前（或指定）模型是否支持图片多模态输入。"""
    cfg = get_model_config(model_id)
    return bool(cfg and cfg.get("supports_images"))


def get_current_model_id():
    return _current_model_id_var.get()


def set_current_model(model_id):
    """为本次请求切换模型，返回新配置；无效 id 返回 None。"""
    cfg = get_model_config(model_id)
    if cfg is None:
        return None
    _current_model_id_var.set(cfg["id"])
    _current_reasoning_effort_var.set(_default_reasoning_effort(cfg))
    _current_style_var.set(_default_style(cfg))
    _current_use_images_var.set(_default_use_images(cfg))
    with _lock:
        _clients.pop(cfg["id"], None)
    return cfg


def get_current_reasoning_effort():
    """当前 Depth 值；空字符串表示 Default（不上传该参数）"""
    return _current_reasoning_effort_var.get()


def set_current_reasoning_effort(value):
    """设置当前模型的 Depth；空值表示 Default。

    返回新的值；当前模型不支持 reasoning_effort 时返回 None；
    值不在配置列表内时抛出 ValueError。
    """
    cfg = get_model_config()
    if cfg is None or not cfg["reasoning_effort"]:
        return None
    effort = "" if value is None else str(value).strip()
    if effort and effort not in cfg["reasoning_effort"]:
        raise ValueError(
            f"reasoning_effort '{effort}' is not configured for model '{cfg['id']}'"
        )
    _current_reasoning_effort_var.set(effort)
    return effort


def get_current_style():
    """当前 Style 名称；空字符串表示 Default（不上传 temperature）"""
    return _current_style_var.get()


def get_current_use_images():
    """本次请求是否上传 blackboard 图片；未显式设置时按当前模型能力决定。"""
    value = _current_use_images_var.get()
    if value is None:
        return model_supports_images()
    return bool(value)


def set_current_style(value):
    """设置当前模型的 Style；空值表示 Default。

    返回新的值；当前模型不支持 style_temperature 时返回 None；
    样式不在配置字典内时抛出 ValueError。
    """
    cfg = get_model_config()
    styles = (cfg or {}).get("style_temperature") or {}
    if not styles:
        return None
    style = "" if value is None else str(value).strip()
    if style and style not in styles:
        raise ValueError(
            f"style '{style}' is not configured for model '{cfg['id']}'"
        )
    _current_style_var.set(style)
    return style


def get_extra_body(model_id=None):
    """合并本次请求的 extra_body：先放页面选择，再用 extra_params 覆盖。

    Depth -> reasoning_effort；Style -> temperature。
    Default（空字符串）不会写入对应字段。extra_params 中同名字段优先级更高。
    """
    cfg = get_model_config(model_id)
    if cfg is None:
        return {}
    body = {}
    is_current = model_id is None or str(model_id) == get_current_model_id()
    effort = get_current_reasoning_effort() if is_current else ""
    if effort and effort in cfg["reasoning_effort"]:
        body["reasoning_effort"] = effort
    style = get_current_style() if is_current else ""
    if style and style in cfg["style_temperature"]:
        body["temperature"] = cfg["style_temperature"][style]
    body.update(cfg.get("extra_params") or {})
    return body


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
