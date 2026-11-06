from utils.get_config import config_data
from utils.perf_log import record_llm_complete, record_llm_input
from agent.utils.llm_access.LLM import get_model_config, get_extra_body


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


def call_llm(question, llm):
    record_llm_input(len(question))
    model_cfg = get_model_config()
    response = llm.chat.completions.create(
        model=model_cfg["model"],
        messages=[
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": question},
        ],
        stream=False,
        extra_body=get_extra_body(model_cfg["id"])
    )

    record_llm_complete()
    _print_usage(getattr(response, "usage", None))

    answer = response.choices[0].message

    return answer
