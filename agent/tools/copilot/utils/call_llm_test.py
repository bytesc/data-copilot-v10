from utils.perf_log import record_first_chunk, record_llm_complete, record_llm_input
from agent.utils.llm_access.LLM import (
    get_model_config, get_extra_body, get_current_use_images, get_current_session_id,
)
from agent.utils.llm_access.image_input import build_user_content
from data_access.llm_log import record_llm_call, messages_to_json

import time


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
    start = time.monotonic()
    response = llm.chat.completions.create(
        model=model_cfg["model"],
        messages=messages,
        stream=False,
        extra_body=get_extra_body(model_cfg["id"])
    )
    duration_ms = int((time.monotonic() - start) * 1000)
    record_llm_complete()
    _print_usage(getattr(response, "usage", None))

    answer = response.choices[0].message
    record_llm_call(
        session_id=get_current_session_id(),
        input_json=messages_to_json(messages),
        output=answer.content or "",
        usage=getattr(response, "usage", None),
        first_token_ms=None,
        duration_ms=duration_ms,
    )
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
    start = time.monotonic()
    response = llm.chat.completions.create(
        model=model_cfg["model"],
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
        extra_body=get_extra_body(model_cfg["id"])
    )

    full_content = ""
    usage = None
    first_token_ms = None
    for chunk in response:
        if getattr(chunk, "usage", None) is not None:
            usage = chunk.usage
        if chunk.choices:
            delta = chunk.choices[0].delta
            if getattr(delta, 'content', None) is not None:
                if first_token_ms is None:
                    first_token_ms = int((time.monotonic() - start) * 1000)
                content_delta = delta.content
                full_content += content_delta
                record_first_chunk()
                print(content_delta, end="", flush=True)
                yield content_delta, None
            if getattr(delta, 'reasoning_content', None) is not None:
                reasoning_delta = delta.reasoning_content
                yield None, reasoning_delta
    duration_ms = int((time.monotonic() - start) * 1000)
    record_llm_complete()
    print()
    _print_usage(usage)

    record_llm_call(
        session_id=get_current_session_id(),
        input_json=messages_to_json(messages),
        output=full_content,
        usage=usage,
        first_token_ms=first_token_ms,
        duration_ms=duration_ms,
    )