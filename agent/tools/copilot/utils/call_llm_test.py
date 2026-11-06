from utils.get_config import config_data
from utils.perf_log import record_first_chunk, record_llm_complete, record_llm_input
from agent.utils.llm_access.LLM import get_model_config, get_extra_body, get_current_use_images
from agent.utils.llm_access.image_input import build_user_content

from datetime import datetime
import os
import random
import string

llmlog_dir = "./llmlog"


def _random_str(length=8):
    return ''.join(random.choices(string.ascii_lowercase, k=length))


def _write_llmlog(question, answer):
    os.makedirs(llmlog_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}-{_random_str()}.txt"
    filepath = os.path.join(llmlog_dir, filename)
    content = f"INPUT:\n{question}\n\nOUTPUT:\n{answer}"
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        print(f"Error writing llmlog: {e}")


def _build_messages(question, model_cfg, images=None):
    content = question
    if images and model_cfg.get("supports_images") and get_current_use_images():
        content = build_user_content(question, images)
    return [{"role": "user", "content": content}]


def _count_message_images(messages):
    content = messages[0].get("content") if messages else None
    if not isinstance(content, list):
        return 0
    return sum(
        1 for part in content
        if isinstance(part, dict) and part.get("type") == "image_url"
    )


def _print_usage(usage):
    if usage is None:
        print("[llm usage] token usage not available")
        return
    parts = [
        f"prompt_tokens={getattr(usage, 'prompt_tokens', None)}",
        f"completion_tokens={getattr(usage, 'completion_tokens', None)}",
        f"total_tokens={getattr(usage, 'total_tokens', None)}",
    ]
    details = getattr(usage, "completion_tokens_details", None)
    reasoning_tokens = getattr(details, "reasoning_tokens", None) if details is not None else None
    if reasoning_tokens is not None:
        parts.append(f"reasoning_tokens={reasoning_tokens}")
    print(f"[llm usage] {' '.join(parts)}")


def call_llm(question, llm, images=None):
    model_cfg = get_model_config()
    messages = _build_messages(question, model_cfg, images)
    print("question len : ", len(question), " model:", model_cfg["id"], " images:", _count_message_images(messages))
    record_llm_input(len(question))
    response = llm.chat.completions.create(
        model=model_cfg["model"],
        messages=messages,
        stream=False,
        extra_body=get_extra_body(model_cfg["id"])
    )
    record_llm_complete()
    _print_usage(getattr(response, "usage", None))

    answer = response.choices[0].message
    if config_data.get("enable_llmlog", False):
        _write_llmlog(question, answer.content)
    return answer


def call_llm_stream(question, llm, images=None):
    for content, _ in _call_llm_stream_events(question, llm, images):
        if content:
            yield content


def call_llm_stream_with_reasoning(question, llm, images=None):
    yield from _call_llm_stream_events(question, llm, images)


def _call_llm_stream_events(question, llm, images=None):
    model_cfg = get_model_config()
    messages = _build_messages(question, model_cfg, images)
    print("question len (stream): ", len(question), " model:", model_cfg["id"], " images:", _count_message_images(messages))
    record_llm_input(len(question))
    response = llm.chat.completions.create(
        model=model_cfg["model"],
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
        extra_body=get_extra_body(model_cfg["id"])
    )

    full_content = ""
    usage = None
    for chunk in response:
        if getattr(chunk, "usage", None) is not None:
            usage = chunk.usage
        if chunk.choices:
            delta = chunk.choices[0].delta
            if getattr(delta, 'content', None) is not None:
                content_delta = delta.content
                full_content += content_delta
                record_first_chunk()
                print(content_delta, end="", flush=True)
                yield content_delta, None
            if getattr(delta, 'reasoning_content', None) is not None:
                reasoning_delta = delta.reasoning_content
                yield None, reasoning_delta
    record_llm_complete()
    print()
    _print_usage(usage)

    if config_data.get("enable_llmlog", False):
        _write_llmlog(question, full_content)