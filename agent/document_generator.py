import json
import os
from typing import List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.tools.tools_def import llm
from agent.tools.copilot.utils.call_llm_test import call_llm_stream, call_llm
from agent.utils.pd_to_walker import generate_random_string
from agent.utils.get_config import config_data

router = APIRouter()


class DocumentInput(BaseModel):
    conversation_history: List[str]
    session_id: Optional[str] = None


OUTLINE_SYSTEM = """You are a business document outline generator. Based on the conversation history between a user and a data analysis AI assistant, generate a structured outline for a business summary document.

The outline should:
1. Have a clear, business-oriented title that reflects the analytical goal
2. Break the conversation into logical parts (typically 3-8 parts), focusing on business insights and conclusions
3. Each part should have a heading and a brief description of what business content to cover

IMPORTANT:
- This is a business summary document. The outline should focus on business analysis, data insights, and conclusions. Do NOT include sections about code, SQL queries, technical implementation details, or agent execution process.
- The entire document MUST be written in the same language as the user's original question in the conversation history.

Output ONLY a valid JSON object (no markdown, no code blocks):
{
  "title": "string",
  "parts": [
    {"heading": "string", "description": "string"}
  ]
}"""


PART_SYSTEM = """You are a professional business document writer. Based on the conversation history between a user and a data analysis AI assistant, write the content for a specific section of a business summary document.

Rules:
1. Write in markdown format
2. Focus on business insights, data analysis results, trends, patterns, and conclusions
3. You may mention data sources and filtering criteria when relevant to the business context
4. Do NOT include code snippets, SQL queries, Python code, or any technical implementation details
5. Do NOT describe the agent's execution process, tool calls, or workflow steps
6. If the conversation history contains successfully generated charts or images (URLs like tmp_imgs/*.png), only include the images that are directly relevant to this specific section's topic — do NOT repeat the same image across multiple sections
7. The entire document MUST be written in the same language as the user's original question in the conversation history
8. Keep the content focused on the section topic
9. Be thorough but concise
10. Use proper markdown headings, lists, and tables as needed (but no code blocks)"""


def _parse_outline_json(raw: str) -> dict:
    raw = raw.strip()
    for prefix in ('```json', '```'):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
    for suffix in ('```',):
        if raw.endswith(suffix):
            raw = raw[:-len(suffix)]
    raw = raw.strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return {"title": "Summary Document", "parts": []}
    if not isinstance(result, dict):
        return {"title": "Summary Document", "parts": []}
    return {
        "title": result.get("title", "Summary Document"),
        "parts": result.get("parts", [])
    }


def _event_stream_generate_document(conversation_history: List[str], session_id: str):
    context = "\n".join(conversation_history)

    yield f"data: {json.dumps({'phase': 'outline', 'type': 'msg', 'content': 'Generating document outline...'}, ensure_ascii=False)}\n\n"

    outline_prompt = f"""{OUTLINE_SYSTEM}

Conversation History:
{context}"""

    outline_raw = ""
    for chunk in call_llm_stream(outline_prompt, llm):
        outline_raw += chunk
        yield f"data: {json.dumps({'phase': 'outline', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

    outline = _parse_outline_json(outline_raw)
    yield f"data: {json.dumps({'phase': 'outline', 'type': 'done', 'content': outline_raw, 'outline': outline}, ensure_ascii=False)}\n\n"

    parts = outline.get("parts", [])
    title = outline.get("title", "Summary Document")

    if not parts:
        yield f"data: {json.dumps({'phase': 'outline', 'type': 'error', 'content': 'No parts generated in outline'}, ensure_ascii=False)}\n\n"
        return

    document_parts = []
    for i, part in enumerate(parts):
        heading = part.get("heading", f"Part {i + 1}")
        description = part.get("description", "")

        yield f"data: {json.dumps({'phase': 'part', 'type': 'msg', 'content': f'Generating part {i + 1}/{len(parts)}: {heading}', 'part_index': i, 'heading': heading}, ensure_ascii=False)}\n\n"

        part_prompt = f"""{PART_SYSTEM}

Document Title: {title}
Section Heading: {heading}
Section Description: {description}

Conversation History:
{context}

Write the content for the section "{heading}" in markdown format. Do NOT include the section heading itself (it will be added automatically)."""

        part_raw = ""
        for chunk in call_llm_stream(part_prompt, llm):
            part_raw += chunk
            yield f"data: {json.dumps({'phase': 'part', 'type': 'chunk', 'content': chunk, 'part_index': i}, ensure_ascii=False)}\n\n"

        document_parts.append((heading, part_raw))
        yield f"data: {json.dumps({'phase': 'part', 'type': 'done', 'content': part_raw, 'part_index': i, 'heading': heading}, ensure_ascii=False)}\n\n"

    full_document = f"# {title}\n\n"
    for heading, content in document_parts:
        full_document += f"## {heading}\n\n{content}\n\n"

    file_name = f"doc_{generate_random_string(8)}.md"
    os.makedirs("tmp_imgs", exist_ok=True)
    file_path = os.path.join("tmp_imgs", file_name)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(full_document)

    static_url = config_data.get("static_path", "http://127.0.0.1:8009/")
    download_url = static_url.rstrip("/") + "/tmp_imgs/" + file_name

    yield f"data: {json.dumps({'phase': 'document', 'type': 'done', 'content': full_document, 'title': title, 'parts_count': len(parts), 'file_name': file_name, 'download_url': download_url}, ensure_ascii=False)}\n\n"


@router.post("/api/generate-document/stream/")
async def generate_document_stream_api(request: Request, user_input: DocumentInput):
    return StreamingResponse(
        _event_stream_generate_document(
            user_input.conversation_history,
            user_input.session_id or "",
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )