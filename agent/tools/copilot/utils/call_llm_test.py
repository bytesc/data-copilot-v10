from utils.get_config import config_data
from utils.perf_log import record_first_chunk, record_llm_complete, record_llm_input

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


def call_llm(question, llm):
    print("question len : ", len(question))
    record_llm_input(len(question))
    response = llm.chat.completions.create(
        model=config_data["model_name"],
        messages=[
            {"role": "user", "content": question},
        ],
        stream=False
    )
    record_llm_complete()

    answer = response.choices[0].message
    if config_data.get("enable_llmlog", False):
        _write_llmlog(question, answer.content)
    return answer


def call_llm_stream(question, llm):
    print("question len (stream): ", len(question))
    record_llm_input(len(question))
    response = llm.chat.completions.create(
        model=config_data["model_name"],
        messages=[
            {"role": "user", "content": question},
        ],
        stream=True
    )

    full_content = ""
    for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content is not None:
            delta = chunk.choices[0].delta.content
            full_content += delta
            record_first_chunk()
            print(delta, end="", flush=True)
            yield delta
    record_llm_complete()
    print()

    if config_data.get("enable_llmlog", False):
        _write_llmlog(question, full_content)