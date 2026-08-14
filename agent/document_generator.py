import json
from typing import List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.tools.tools_def import llm
from agent.tools.copilot.utils.call_llm_test import call_llm_stream, call_llm

router = APIRouter()


class DocumentInput(BaseModel):
    conversation_history: List[str]
    session_id: Optional[str] = None


OUTLINE_SYSTEM = """You are a document outline generator. Based on the conversation history between a user and a data analysis AI assistant, generate a structured outline for a summary document.

The outline should:
1. Have a clear, descriptive title
2. Break the conversation into logical parts (typically 3-8 parts)
3. Each part should have a heading and a brief description of what to cover

Output ONLY a valid JSON object (no markdown, no code blocks):
{
  "title": "string",
  "parts": [
    {"heading": "string", "description": "string"}
  ]
}"""


PART_SYSTEM = """You are a professional document writer. Based on the conversation history between a user and a data analysis AI assistant, write the content for a specific section of a summary document.

Rules:
1. Write in markdown format
2. Include relevant details, data, code snippets, and conclusions from the conversation
3. Keep the content focused on the section topic
4. Be thorough but concise
5. Use proper markdown headings, lists, tables, and code blocks as needed"""


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

    yield f"data: {json.dumps({'phase': 'document', 'type': 'done', 'content': full_document, 'title': title, 'parts_count': len(parts)}, ensure_ascii=False)}\n\n"


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