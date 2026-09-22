import json
import os
import re
import io
from typing import List, Optional, Set

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

router = APIRouter()

from markdown_pdf import MarkdownPdf, Section

from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

from agent.tools.base_knowledge.get_base_knowledge import DOC, TARGET, BASE
from agent.tools.tools_def import llm
from agent.tools.copilot.utils.call_llm_test import call_llm_stream, call_llm
from agent.utils.pd_to_walker import generate_random_string
from agent.utils.get_config import config_data
from data_access.session_log import record_session_operation

_ENABLE_TARGET = config_data.get('enable_target_knowledge', False)
from data_access.observe_log import log_observe_cycle
from data_access.report_log import record_report_generation
from utils.front_utils import history_to_text

DOC_WORKSPACE = "doc_workspace"
os.makedirs(DOC_WORKSPACE, exist_ok=True)


class DocumentInput(BaseModel):
    conversation_history: List[dict]
    session_id: Optional[str] = None


class YamlOutlineInput(BaseModel):
    conversation_history: List[dict]
    session_id: Optional[str] = None


class SectionContent(BaseModel):
    heading: str
    content: str

class YamlDocumentInput(BaseModel):
    conversation_history: List[dict]
    yaml_outline: str
    session_id: Optional[str] = None
    section_index: Optional[int] = None
    confirmed_sections: Optional[List[SectionContent]] = None
    yaml_base: Optional[str] = None


class FinalizeInput(BaseModel):
    markdown_content: str
    session_id: Optional[str] = None
    yaml_base: Optional[str] = None
    conversation_history: Optional[List[dict]] = None


OUTLINE_SYSTEM = """You are a business document outline generator. Based on the conversation history between a user and a data analysis AI assistant, generate a structured outline for a business summary document.

The outline should:
1. Have a clear, business-oriented title that reflects the analytical goal
2. Break the conversation into logical parts (typically 3-8 parts), focusing on business insights and conclusions
3. Each part should have a heading and a brief description of what business content to cover

IMPORTANT:
- This is a business summary document. The outline should focus on business analysis, data insights, and conclusions. Do NOT include sections about code, SQL queries, technical implementation details, or agent execution process.
- CRITICAL: The output must contain NO code whatsoever. No code blocks, no inline code snippets, no SQL, no Python, no YAML, no chart syntax, no programming language constructs of any kind.
- LANGUAGE IS CRITICAL: The entire document MUST be written in the EXACT SAME language as the user's original question. If the user asked in English, write in English. If the user asked in Chinese, write in Chinese. The conversation history and knowledge base below are provided for factual content ONLY — they may contain mixed or different languages. You MUST ignore their language entirely and write exclusively in the user's language. This is not a suggestion — it is a hard requirement. The language of agent outputs, SQL results, knowledge base, or any other context must NEVER leak into the output.
- The final part (if structured as a summary or conclusion) must synthesize the key findings into concise, actionable insights. It must NOT repeat the headings or structure of the earlier parts. It should answer "so what" and "what to do next," not re-list the document sections. The description of the final part must NOT use phrases like "summarize each section" or "recap the key points from each section" — it should describe a synthesis of cross-cutting conclusions.
- IMPORTANT — CHARTS AND IMAGES: The conversation history contains data analysis results with generated charts and images. When planning the outline, consider which charts are available and assign them to the most relevant parts. Each part should reference at least one chart if suitable charts exist in the context. Do NOT create a separate section just for charts — integrate them naturally into the business analysis sections.

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
4. CRITICAL: The output must contain NO code whatsoever. No code blocks, no inline code snippets, no SQL, no Python, no YAML, no chart syntax, no programming language constructs of any kind.
5. Do NOT describe the agent's execution process, tool calls, or workflow steps
6. CHARTS AND IMAGES ARE REQUIRED: The conversation history contains successfully generated charts and images (URLs like tmp_imgs/*.png). You MUST include every valid chart and image from the context that is relevant to this section's topic. Use markdown image syntax: `![description](image_url)`. Reference the actual image URLs from the conversation history — do NOT make up URLs. Place each chart near the text that discusses its findings. Do NOT repeat the same image across multiple sections — if the prompt lists "already used" images, strictly avoid including them. Each chart should appear in exactly one section (the most relevant one).
7. LANGUAGE IS CRITICAL — READ THIS FIRST: Before writing anything, check the "Document Title" below. If it is in English, write this entire section in English. If it is in Chinese, write in Chinese. The conversation history and knowledge base below are provided for factual content ONLY — they may contain mixed or different languages. You MUST ignore their language entirely and write exclusively in the language of the Document Title. This is not a suggestion — it is a hard requirement. The knowledge base (which is a Chinese document about Singapore regulations) must NEVER influence the output language. Every sentence you write must be in the Document Title's language.
8. Keep the content focused on the section topic
9. Be thorough but concise
10. Use proper markdown headings, lists, and tables as needed. Do NOT use any fenced code blocks. Heading depth is limited to `###` (H3) — do NOT use `####`, `#####`, or `######`. Use `###` for sub-headings and plain bold text or bullet points for deeper structure.
11. ⚠️ Do NOT add numbers to sub-headings (e.g., avoid `### 1. xxx`, `### 2. xxx`). Use descriptive headings only, like `### Key Findings` or `### 核心发现`. Numbered lists in body text are allowed but use `-` bullet lists instead of `1.` numbered lists to avoid Word auto-numbering conflicts.
11. Sub-headings within this section MAY use numbering (e.g., `### 1. xxx`), but the numbering MUST restart from 1 for THIS section only — do NOT continue numbering from previous sections. Each section is independent; its sub-heading numbers are scoped to this section alone.
12. If this section is the final summary or conclusion: do NOT create sub-sections that mirror the earlier section headings. Do NOT structure the summary as a list of per-topic recaps. Instead, synthesize cross-cutting themes into a few concise, actionable recommendations. Answer "so what" and "what to do next." The summary should be shorter than the other sections, not longer.
"""


UNIFIED_SYSTEM = """You are a professional business document writer. Based on the conversation history between a user and a data analysis AI assistant, write the complete business summary document in one pass.

You must follow the structural directive below exactly:

**Structural Requirements:**
- Present the overall conclusion first (Executive Summary), followed by the detailed breakdown and supporting analysis.
- The "conclusion-first" structure applies to every subsection. Each subsection must open with its own key conclusion or finding, followed by the supporting analysis, evidence, or data. No subsection may begin with background information or context before stating its primary conclusion.
- Use a clear hierarchical heading structure. The document should have a top-level title (`# Title`), major sections (`## Section`), and subsections as needed (`### Subsection`, `#### Subsection`). There is no restriction on heading depth.
- Numbered headings (e.g. `## 1. Introduction`, `### 3.1 Clinical sites`) are allowed and encouraged for clarity.

**Content Rules:**
1. Write entirely in markdown format.
2. CRITICAL: The output must contain NO code blocks. No fenced code, no inline code snippets, no SQL, no Python, no YAML, no chart syntax. Use plain markdown (headings, lists, tables, bold, italic) only.
3. Focus on business insights, data analysis results, trends, patterns, and conclusions.
4. Do NOT describe the agent's execution process, tool calls, search steps, data collection methods, or analytical workflows. Present only the final findings.
5. CHARTS AND IMAGES: The conversation history contains successfully generated charts and images (URLs like tmp_imgs/*.png). You MUST include every valid chart and image that is relevant. Use markdown image syntax: `![description](image_url)`. Reference actual image URLs from the conversation — do NOT make up URLs. Place each chart near the text that discusses its findings.
6. LANGUAGE IS CRITICAL: Determine the user's language from the conversation history. Write the entire document in that language. The knowledge base and other context may contain mixed languages — ignore them. Every sentence must be in the user's language.
7. You may mention data sources and filtering criteria when relevant to the business context.
8. Be thorough but concise.
9. All tables must be well-formatted markdown tables.
10. If the conversation history does not contain enough data for a meaningful section, state what is not available rather than inventing data.
"""


YAML_OUTLINE_SYSTEM = """You are a business document outline generator. Based on the conversation history, generate a YAML outline that defines the document structure.

The YAML must follow this exact structure:
```yaml
title: "Document Title"
sections:
  - heading: "1. Section Heading"
    description: "Brief description of what this section covers"
    subsections:
      - heading: "1.1 Subsection Heading"
        description: "Brief description"

Rules:
1. Use numbered headings for clarity (1., 1.1, 2., etc.)
2. Each section can have 0 or more subsections
3. Keep descriptions concise (1-2 sentences)
4. Focus on business insights and data analysis — no technical implementation details
5. LANGUAGE IS CRITICAL: Write the title and all headings in the EXACT SAME LANGUAGE as the user's original question.

Output ONLY valid YAML inside a ```yaml code block. Do not include any other text."""


YAML_PART_SYSTEM = """You are a professional business document writer. Based on the conversation history and the document outline below, write the content for a specific section of the document.

Rules:
1. Write in markdown format. Start with the section heading as `## Heading`.
2. Focus on business insights, data analysis results, trends, patterns, and conclusions.
3. CRITICAL: The output must contain NO code blocks, no SQL, no Python, no YAML.
4. Do NOT describe the agent's execution process, tool calls, or workflow steps.
5. CHARTS AND IMAGES: Include relevant charts from the conversation history. Use markdown image syntax: `![description](image_url)`. Reference actual image URLs — do NOT make up URLs. Do NOT repeat images already used in other sections — if the prompt lists "already used" images below, strictly avoid them.
6. LANGUAGE IS CRITICAL: Write in the EXACT SAME LANGUAGE as the Document Title below. Ignore the language of the conversation history or knowledge base.
7. Be thorough but concise.
8. Use proper markdown headings (up to `###`), lists, and tables as needed.
9. If this section has sub-sections listed in the outline, include each sub-section's heading as `### Subsection Heading` and write its content. The heading text must appear ONLY as the `###` marker — do NOT repeat it in the content body.

Document Title: {title}
Section Heading: {heading}
Section Description: {description}

Full Outline (all sections):
{outline_overview}

{used_hint}

Write the content for the section "{heading}". Do NOT repeat the heading — it will be added automatically. Start directly with the content. For any subsection, use `### Subsection Heading` as the only occurrence of that heading text — do NOT repeat it in the body."""


def _extract_image_urls(text: str) -> Set[str]:
    return set(re.findall(r'!\[[^\]]*\]\(([^)]+)\)', text))


def _download_image_bytes(url: str) -> bytes:
    static_folder = config_data.get("static_folder", "tmp_imgs")
    local_match = re.search(rf'{re.escape(static_folder)}/([^\s/]+\.(?:png|jpg|jpeg|gif|bmp|webp))', url, re.IGNORECASE)
    if local_match:
        local_path = os.path.join(static_folder, local_match.group(1))
        if os.path.isfile(local_path):
            with open(local_path, "rb") as f:
                return f.read()
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True)
        if resp.status_code == 200:
            return resp.content
    except Exception:
        pass
    return b""


def _markdown_to_docx(markdown_text: str, output_path: str):
    doc = Document()
    style = doc.styles['Normal']
    style.font.size = Pt(11)
    style.font.name = 'Calibri'

    lines = markdown_text.split('\n')
    i = 0
    title_centered = False
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2)
            p = doc.add_heading(level=min(level, 3))
            if level == 1 and not title_centered:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                title_centered = True
            _add_inline_runs(p, text)
            i += 1
            continue

        ul_match = re.match(r'^[-*+]\s+(.+)$', stripped)
        if ul_match:
            p = doc.add_paragraph(style='List Bullet')
            _add_inline_runs(p, ul_match.group(1))
            i += 1
            continue

        ol_match = re.match(r'^\d+\.\s+(.+)$', stripped)
        if ol_match:
            p = doc.add_paragraph()
            _add_inline_runs(p, stripped)
            i += 1
            continue

        img_match = re.match(r'^!\[([^\]]*)\]\(([^)]+)\)$', stripped)
        if img_match:
            alt_text = img_match.group(1)
            img_url = img_match.group(2)
            img_bytes = _download_image_bytes(img_url)
            if img_bytes:
                try:
                    img_stream = io.BytesIO(img_bytes)
                    doc.add_picture(img_stream, width=Inches(5.5))
                    last_paragraph = doc.paragraphs[-1] if doc.paragraphs else doc.add_paragraph()
                    last_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    if alt_text:
                        caption = doc.add_paragraph()
                        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        run = caption.add_run(alt_text)
                        run.font.size = Pt(9)
                        run.italic = True
                except Exception:
                    p = doc.add_paragraph()
                    run = p.add_run(f'[Image: {alt_text}]')
                    run.italic = True
            else:
                p = doc.add_paragraph()
                run = p.add_run(f'[Image: {alt_text}]')
                run.italic = True
            i += 1
            continue

        if stripped.startswith('|') and '|' in stripped[1:]:
            table_rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                row_line = lines[i].strip()
                if re.match(r'^[\|\s\-:]+$', row_line):
                    i += 1
                    continue
                cells = [c.strip() for c in row_line.split('|')[1:-1]]
                table_rows.append(cells)
                i += 1
            if table_rows:
                table = doc.add_table(rows=len(table_rows), cols=len(table_rows[0]))
                table.style = 'Light Grid Accent 1'
                for ri, row in enumerate(table_rows):
                    for ci, cell_text in enumerate(row):
                        cell = table.rows[ri].cells[ci]
                        cell.text = ''
                        p = cell.paragraphs[0]
                        _add_inline_runs(p, cell_text)
            continue

        p = doc.add_paragraph()
        _add_inline_runs(p, stripped)
        i += 1

    doc.save(output_path)


def _markdown_to_pdf(markdown_text: str, output_path: str):
    def _embed_image(match):
        alt_text = match.group(1)
        img_url = match.group(2)
        img_bytes = _download_image_bytes(img_url)
        if img_bytes:
            import base64
            ext = os.path.splitext(img_url.split("?")[0])[1].lstrip(".") or "png"
            if ext.lower() in ("jpg", "jpeg"):
                ext = "jpeg"
            b64 = base64.b64encode(img_bytes).decode("ascii")
            return f'![{alt_text}](data:image/{ext};base64,{b64})'
        return f'*[Image: {alt_text}]*'

    markdown_text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', _embed_image, markdown_text)

    pdf = MarkdownPdf()
    pdf.add_section(Section(markdown_text, toc=False))
    pdf.save(output_path)


def _add_inline_runs(paragraph, text: str):
    pattern = re.compile(r'(\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`|!\[([^\]]*)\]\(([^)]+)\)|\[([^\]]+)\]\(([^)]+)\))')
    last_end = 0
    for m in pattern.finditer(text):
        if m.start() > last_end:
            paragraph.add_run(text[last_end:m.start()])
        if m.group(2):
            run = paragraph.add_run(m.group(2))
            run.bold = True
        elif m.group(3):
            run = paragraph.add_run(m.group(3))
            run.italic = True
        elif m.group(4):
            run = paragraph.add_run(m.group(4))
            run.font.name = 'Consolas'
            run.font.size = Pt(10)
        elif m.group(5):
            run = paragraph.add_run(f'[Image: {m.group(5)}]')
            run.italic = True
            run.font.size = Pt(9)
        elif m.group(7):
            run = paragraph.add_run(m.group(7))
            run.underline = True
        last_end = m.end()
    if last_end < len(text):
        paragraph.add_run(text[last_end:])


def _parse_outline_json(raw: str) -> dict:
    from utils.context_trim import parse_json
    result = parse_json(raw)
    if isinstance(result, dict):
        return {
            "title": result.get("title", "Summary Document"),
            "parts": result.get("parts", [])
        }
    return {"title": "Summary Document", "parts": []}


def _parse_yaml_outline(raw: str) -> str:
    match = re.search(r'```(?:yaml)?\s*\n(.*?)```', raw, re.DOTALL)
    if match:
        return match.group(1).strip()
    return raw.strip()


def _parse_yaml_sections(yaml_str: str) -> dict:
    import yaml as _yaml
    try:
        data = _yaml.safe_load(yaml_str)
        if not isinstance(data, dict):
            return {"title": "Summary Document", "sections": []}
        title = data.get("title", "Summary Document")
        raw_sections = data.get("sections", [])
        sections = []
        for s in raw_sections:
            section = {
                "heading": s.get("heading", ""),
                "description": s.get("description", ""),
                "subsections": []
            }
            for sub in s.get("subsections", []):
                section["subsections"].append({
                    "heading": sub.get("heading", ""),
                    "description": sub.get("description", ""),
                })
            sections.append(section)
        return {"title": title, "sections": sections}
    except Exception:
        return {"title": "Summary Document", "sections": []}


def _save_intermediate_yaml(yaml_str: str, base_name: str, session_id: str = "") -> str:
    prefix = f"{session_id}_" if session_id else ""
    file_name = f"outline_{prefix}{base_name}.yaml"
    path = os.path.join(DOC_WORKSPACE, file_name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(yaml_str)
    return file_name


def _save_intermediate_markdown(markdown_text: str, base_name: str, session_id: str = "") -> str:
    prefix = f"{session_id}_" if session_id else ""
    file_name = f"draft_{prefix}{base_name}.md"
    path = os.path.join(DOC_WORKSPACE, file_name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(markdown_text)
    return file_name


def _event_stream_generate_document(conversation_history: List[dict], session_id: str, request_json: str = ""):
    context = history_to_text(conversation_history)

    _target_section = str(TARGET) if _ENABLE_TARGET else ""

    yield f"data: {json.dumps({'phase': 'outline', 'type': 'msg', 'content': 'Generating document outline...'}, ensure_ascii=False)}\n\n"

    outline_prompt = f"""{OUTLINE_SYSTEM}

{BASE}

{DOC}

{_target_section if _ENABLE_TARGET else ""}

Conversation History:
{context}"""

    outline_raw = ""
    for chunk in call_llm_stream(outline_prompt, llm):
        outline_raw += chunk
        yield f"data: {json.dumps({'phase': 'outline', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

    outline = _parse_outline_json(outline_raw)
    yield f"data: {json.dumps({'phase': 'outline', 'type': 'done', 'content': outline_raw, 'outline': outline}, ensure_ascii=False)}\n\n"

    log_observe_cycle(session_id, 0, "generate_document", "outline",
                      prompt=outline_prompt[:10000], response=outline_raw[:10000],
                      token_estimate=len(outline_prompt) // 3)

    parts = outline.get("parts", [])
    title = outline.get("title", "Summary Document")

    if not parts:
        yield f"data: {json.dumps({'phase': 'outline', 'type': 'error', 'content': 'No parts generated in outline'}, ensure_ascii=False)}\n\n"
        return

    document_parts = []
    used_images: Set[str] = set()
    for i, part in enumerate(parts):
        heading = part.get("heading", f"Part {i + 1}")
        description = part.get("description", "")

        yield f"data: {json.dumps({'phase': 'part', 'type': 'msg', 'content': f'Generating part {i + 1}/{len(parts)}: {heading}', 'part_index': i, 'heading': heading}, ensure_ascii=False)}\n\n"

        used_hint = ""
        if used_images:
            used_list = "\n".join(f"- {url}" for url in sorted(used_images))
            used_hint = f"\n\nIMPORTANT: The following images have already been used in previous sections. Do NOT include them again:\n{used_list}\n"

        part_prompt = f"""{PART_SYSTEM}

Document Title: {title}
Section Heading: {heading}
Section Description: {description}{used_hint}

Full Document Outline (all sections):
{chr(10).join(f'  {j+1}. {p["heading"]} — {p["description"]}' for j, p in enumerate(parts))}

{BASE}

{DOC}

{_target_section}

Conversation History:
{context}

Write the content for the section "{heading}" in markdown format. ⚠️ CRITICAL: Do NOT repeat the section heading "{heading}" in your output. The heading will be added automatically. Start directly with the body content — no heading, no title line."""

        part_raw = ""
        for chunk in call_llm_stream(part_prompt, llm):
            part_raw += chunk
            yield f"data: {json.dumps({'phase': 'part', 'type': 'chunk', 'content': chunk, 'part_index': i}, ensure_ascii=False)}\n\n"

        new_images = _extract_image_urls(part_raw)
        used_images.update(new_images)

        document_parts.append((heading, part_raw))
        yield f"data: {json.dumps({'phase': 'part', 'type': 'done', 'content': part_raw, 'part_index': i, 'heading': heading}, ensure_ascii=False)}\n\n"

        log_observe_cycle(session_id, i + 1, "generate_document", "part",
                          prompt=part_prompt[:10000], response=part_raw[:10000],
                          token_estimate=len(part_prompt) // 3)

    full_document = f"# {title}\n\n"
    for idx, (heading, content) in enumerate(document_parts, 1):
        full_document += f"## {idx}. {heading}\n\n{content}\n\n"

    full_document = re.sub(r'```[a-z]*\n.*?```\n?', '', full_document, flags=re.DOTALL)

    file_name = f"doc_{generate_random_string(8)}"
    static_folder = config_data.get("static_folder", "tmp_imgs")
    os.makedirs(static_folder, exist_ok=True)

    md_path = os.path.join(static_folder, file_name + ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(full_document)

    docx_path = os.path.join(static_folder, file_name + ".docx")
    try:
        _markdown_to_docx(full_document, docx_path)
    except Exception:
        docx_path = None

    pdf_path = os.path.join(static_folder, file_name + ".pdf")
    try:
        _markdown_to_pdf(full_document, pdf_path)
    except Exception:
        pdf_path = None

    static_url = config_data["static_path"].rstrip("/")
    static_folder = config_data.get("static_folder", "tmp_imgs")
    download_url_md = f"{static_url}/{static_folder}/{file_name}.md"
    download_url_docx = f"{static_url}/{static_folder}/{file_name}.docx" if docx_path else ""
    download_url_pdf = f"{static_url}/{static_folder}/{file_name}.pdf" if pdf_path else ""

    yield f"data: {json.dumps({'phase': 'document', 'type': 'done', 'content': full_document, 'title': title, 'parts_count': len(parts), 'file_name': file_name, 'download_url_md': download_url_md, 'download_url_docx': download_url_docx, 'download_url_pdf': download_url_pdf, 'conversation_history': conversation_history}, ensure_ascii=False)}\n\n"

    record_session_operation(
        session_id, "/api/generate-document/stream/",
        request_json, full_document[:5000], "",
        "success", f"Document generated: {title}, {len(parts)} parts",
        prompt_length=len(context)
    )

    outline_json = json.dumps({"title": title}, ensure_ascii=False)

    record_report_generation(
        session_id=session_id,
        file_name=file_name,
        chat_history=json.dumps(conversation_history, ensure_ascii=False),
        outline=outline_json,
        full_text=full_document,
    )


@router.post("/api/generate-document/stream/")
async def generate_document_stream_api(request: Request, user_input: DocumentInput):
    return StreamingResponse(
        _event_stream_generate_document(
            user_input.conversation_history,
            user_input.session_id or "",
            user_input.model_dump_json(),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


def generate_document_from_context(conversation_history: List[dict], session_id: str, title: str = "", request_json: str = ""):
    yield from _event_stream_generate_document_unified(conversation_history, session_id, title, request_json)


def _event_stream_generate_document_unified(conversation_history: List[dict], session_id: str, title: str = "", request_json: str = ""):
    context = history_to_text(conversation_history)
    _target_section = str(TARGET) if _ENABLE_TARGET else ""

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'generate_document', 'type': 'msg', 'content': 'Generating document...'}, ensure_ascii=False)}\n\n"

    prompt = f"""{UNIFIED_SYSTEM}

{BASE}

{DOC}

{_target_section}

Conversation History:
{context}

Write the complete business summary document in markdown format. Start with `# Title` as the top-level heading. Do NOT wrap the output in any code blocks or fences — output raw markdown only. Do NOT include any introductory or explanatory text outside the markdown document."""

    full_raw = ""
    for chunk in call_llm_stream(prompt, llm):
        full_raw += chunk
        yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'generate_document', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'generate_document', 'type': 'done', 'content': full_raw}, ensure_ascii=False)}\n\n"

    log_observe_cycle(session_id, 0, "generate_document_unified", "full",
                      prompt=prompt[:10000], response=full_raw[:10000],
                      token_estimate=len(prompt) // 3)

    full_document = re.sub(r'```[a-z]*\n.*?```\n?', '', full_raw, flags=re.DOTALL)

    title_match = re.search(r'^#\s+(.+)$', full_document, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "Summary Document"

    file_name = f"doc_{generate_random_string(8)}"
    static_folder = config_data.get("static_folder", "tmp_imgs")
    os.makedirs(static_folder, exist_ok=True)

    md_path = os.path.join(static_folder, file_name + ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(full_document)

    docx_path = os.path.join(static_folder, file_name + ".docx")
    try:
        _markdown_to_docx(full_document, docx_path)
    except Exception:
        docx_path = None

    pdf_path = os.path.join(static_folder, file_name + ".pdf")
    try:
        _markdown_to_pdf(full_document, pdf_path)
    except Exception:
        pdf_path = None

    static_url = config_data["static_path"].rstrip("/")
    static_folder = config_data.get("static_folder", "tmp_imgs")
    download_url_md = f"{static_url}/{static_folder}/{file_name}.md"
    download_url_docx = f"{static_url}/{static_folder}/{file_name}.docx" if docx_path else ""
    download_url_pdf = f"{static_url}/{static_folder}/{file_name}.pdf" if pdf_path else ""

    outline_json = json.dumps({"title": title}, ensure_ascii=False)

    yield f"data: {json.dumps({'phase': 'act', 'sub_phase': 'generate_document', 'type': 'done', 'content': full_document, 'title': title, 'file_name': file_name, 'download_url_md': download_url_md, 'download_url_docx': download_url_docx, 'download_url_pdf': download_url_pdf, 'conversation_history': conversation_history}, ensure_ascii=False)}\n\n"

    record_session_operation(
        session_id, "act/generate_document",
        request_json, full_document[:5000], "",
        "success", f"Document generated: {title}",
        prompt_length=len(context)
    )

    record_report_generation(
        session_id=session_id,
        file_name=file_name,
        chat_history=json.dumps(conversation_history, ensure_ascii=False),
        outline=outline_json,
        full_text=full_document,
    )


@router.post("/api/generate-document/stream/unified/")
async def generate_document_unified_stream_api(request: Request, user_input: DocumentInput):
    return StreamingResponse(
        generate_document_from_context(
            user_input.conversation_history,
            user_input.session_id or "",
            user_input.model_dump_json(),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ── YAML Outline generation ──────────────────────────────────────────────


def _event_stream_generate_yaml_outline(conversation_history: List[dict], session_id: str, request_json: str = ""):
    context = history_to_text(conversation_history)
    _target_section = str(TARGET) if _ENABLE_TARGET else ""

    yield f"data: {json.dumps({'phase': 'yaml_outline', 'type': 'msg', 'content': 'Generating YAML outline...'}, ensure_ascii=False)}\n\n"

    prompt = f"""{YAML_OUTLINE_SYSTEM}

{BASE}

{DOC}

{_target_section if _ENABLE_TARGET else ""}

Conversation History:
{context}"""

    error_hint = ""
    for attempt in range(2):
        if attempt > 0:
            yield f"data: {json.dumps({'phase': 'yaml_outline', 'type': 'msg', 'content': 'Parsing failed, re-generating YAML outline...'}, ensure_ascii=False)}\n\n"

        raw = ""
        for chunk in call_llm_stream(prompt + error_hint, llm):
            raw += chunk
            yield f"data: {json.dumps({'phase': 'yaml_outline', 'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

        yaml_str = _parse_yaml_outline(raw)
        parsed = _parse_yaml_sections(yaml_str)
        if parsed.get("sections"):
            break

        error_hint = "\n\nPrevious attempt failed. Output valid YAML inside ```yaml block with proper structure (title + sections list)."
    else:
        yield f"data: {json.dumps({'phase': 'yaml_outline', 'type': 'error', 'content': 'Failed to generate valid YAML outline after retries'}, ensure_ascii=False)}\n\n"
        return

    yaml_base = generate_random_string(8)
    yaml_file_name = _save_intermediate_yaml(yaml_str, yaml_base, session_id)

    log_observe_cycle(session_id, 0, "generate_yaml_outline", "outline",
                      prompt=prompt[:10000], response=raw[:10000],
                      token_estimate=len(prompt) // 3)

    yield f"data: {json.dumps({'phase': 'yaml_outline', 'type': 'done', 'content': yaml_str, 'yaml_file': yaml_file_name, 'yaml_base': yaml_base}, ensure_ascii=False)}\n\n"

    record_session_operation(
        session_id, "/api/generate-document/generate-yaml-outline/",
        request_json, yaml_str[:5000], "",
        "success", f"YAML outline generated: {yaml_file_name}",
        prompt_length=len(context)
    )


@router.post("/api/generate-document/generate-yaml-outline/")
async def generate_yaml_outline_api(request: Request, user_input: YamlOutlineInput):
    return StreamingResponse(
        _event_stream_generate_yaml_outline(
            user_input.conversation_history,
            user_input.session_id or "",
            user_input.model_dump_json(),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ── Section-by-section Markdown generation from YAML ─────────────────────


def _event_stream_generate_from_yaml(conversation_history: List[dict], yaml_outline: str, session_id: str, request_json: str = "", section_index: Optional[int] = None, confirmed_sections: Optional[List[dict]] = None, yaml_base: str = ""):
    context = history_to_text(conversation_history)
    _target_section = str(TARGET) if _ENABLE_TARGET else ""
    yaml_outline = _parse_yaml_outline(yaml_outline)
    parsed = _parse_yaml_sections(yaml_outline)
    if not parsed.get("sections"):
        error_msg = f"Failed to parse YAML outline: no sections found"
        print(f"[ERROR] {error_msg}")
        yield f"data: {json.dumps({'phase': 'document_from_yaml', 'type': 'error', 'content': error_msg}, ensure_ascii=False)}\n\n"
        return

    title = parsed["title"]
    sections = parsed["sections"]
    total = len(sections)

    if section_index is not None:
        sections = [sections[section_index]] if 0 <= section_index < total else []
        if not sections:
            yield f"data: {json.dumps({'phase': 'document_from_yaml', 'type': 'error', 'content': f'Invalid section_index: {section_index}, total: {total}'}, ensure_ascii=False)}\n\n"
            return

    yield f"data: {json.dumps({'phase': 'document_from_yaml', 'type': 'msg', 'content': f'Generating {len(sections)} sections from YAML outline...'}, ensure_ascii=False)}\n\n"

    outline_overview = "\n".join(
        f"  {s['heading']} — {s['description']}"
        + ("".join(f"\n    - {sub['heading']}: {sub['description']}" for sub in s["subsections"]))
        for s in parsed["sections"]
    )

    document_parts = []
    section_files = []
    used_images: Set[str] = set()
    base_name = yaml_base if yaml_base else f"{session_id}_{generate_random_string(8)}" if session_id else generate_random_string(8)

    for i, section in enumerate(sections):
        actual_idx = section_index if section_index is not None else i
        heading = section["heading"]
        description = section["description"]

        yield f"data: {json.dumps({'phase': 'document_from_yaml', 'type': 'section_msg', 'content': f'Generating section {actual_idx + 1}/{total}: {heading}', 'section_index': actual_idx, 'heading': heading, 'total_sections': total}, ensure_ascii=False)}\n\n"

        used_hint = ""
        if used_images:
            used_list = "\n".join(f"- {url}" for url in sorted(used_images))
            used_hint = f"\nAlready used images (DO NOT reuse):\n{used_list}"

        previous_sections_text = ""
        if confirmed_sections:
            prev_parts = []
            for cs in confirmed_sections:
                h = cs.get("heading", "")
                c = cs.get("content", "")
                if h and c:
                    prev_parts.append(f"### {h}\n\n{c}")
            if prev_parts:
                previous_sections_text = "\n\nAlready written sections (read for context — do NOT repeat this content):\n\n" + "\n\n---\n\n".join(prev_parts)

        section_prompt = f"""{YAML_PART_SYSTEM.format(
            title=title,
            heading=heading,
            description=description,
            outline_overview=outline_overview,
            used_hint=used_hint,
        )}

{BASE}

{DOC}

{_target_section}{previous_sections_text}

Conversation History:
{context}

Write the content for the section "{heading}" in markdown format."""

        part_raw = ""
        for chunk in call_llm_stream(section_prompt, llm):
            part_raw += chunk
            yield f"data: {json.dumps({'phase': 'document_from_yaml', 'type': 'chunk', 'content': chunk, 'section_index': i}, ensure_ascii=False)}\n\n"

        new_images = _extract_image_urls(part_raw)
        used_images.update(new_images)

        document_parts.append((heading, part_raw))

        sec_file = f"draft_{base_name}_s{actual_idx:02d}.md"
        sec_path = os.path.join(DOC_WORKSPACE, sec_file)
        with open(sec_path, "w", encoding="utf-8") as f:
            f.write(f"## {heading}\n\n{part_raw}")
        section_files.append({"name": sec_file, "heading": heading, "index": actual_idx})

        yield f"data: {json.dumps({'phase': 'document_from_yaml', 'type': 'section_done', 'content': part_raw, 'section_index': actual_idx, 'heading': heading, 'section_file': sec_file, 'total_sections': total}, ensure_ascii=False)}\n\n"

        log_observe_cycle(session_id, actual_idx + 1, "generate_from_yaml", "part",
                          prompt=section_prompt[:10000], response=part_raw[:10000],
                          token_estimate=len(section_prompt) // 3)

    if section_index is None:
        full_document = f"# {title}\n\n"
        for heading, content in document_parts:
            full_document += f"## {heading}\n\n{content}\n\n"
        full_document = re.sub(r'```[a-z]*\n.*?```\n?', '', full_document, flags=re.DOTALL)
        merged_file = _save_intermediate_markdown(full_document, base_name)
        _done_event = {
            'phase': 'document_from_yaml', 'type': 'done',
            'content': full_document,
            'title': title,
            'md_file': merged_file,
            'section_files': section_files,
            'sections_count': len(sections),
        }
        yield f"data: {json.dumps(_done_event, ensure_ascii=False)}\n\n"
        record_session_operation(
            session_id, "/api/generate-document/stream/from-yaml/",
            request_json, full_document[:5000], "",
            "success", f"Markdown draft generated from YAML: {title}, {len(sections)} sections",
            prompt_length=len(context)
        )
        record_report_generation(
            session_id=session_id,
            file_name=merged_file,
            chat_history=json.dumps(conversation_history, ensure_ascii=False),
            outline=json.dumps({"title": title, "yaml_outline": yaml_outline}, ensure_ascii=False),
            full_text=full_document,
        )


@router.post("/api/generate-document/stream/from-yaml/")
async def generate_document_from_yaml_api(request: Request, user_input: YamlDocumentInput):
    confirmed = [{"heading": s.heading, "content": s.content} for s in (user_input.confirmed_sections or [])]
    return StreamingResponse(
        _event_stream_generate_from_yaml(
            user_input.conversation_history,
            user_input.yaml_outline,
            user_input.session_id or "",
            user_input.model_dump_json(),
            section_index=user_input.section_index,
            confirmed_sections=confirmed,
            yaml_base=user_input.yaml_base or "",
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ── Finalize: convert edited Markdown to docx/pdf ────────────────────────


def _cleanup_workspace_files(base_name: str):
    import glob
    patterns = [
        f"outline_{base_name}.yaml",
        f"draft_{base_name}.md",
        f"draft_{base_name}_s*.md",
    ]
    for pattern in patterns:
        for f in glob.glob(os.path.join(DOC_WORKSPACE, pattern)):
            try:
                os.remove(f)
            except Exception:
                pass


def _event_stream_finalize(markdown_content: str, session_id: str, request_json: str = "", yaml_base: str = "", conversation_history: Optional[List[dict]] = None):
    full_document = re.sub(r'```[a-z]*\n.*?```\n?', '', markdown_content, flags=re.DOTALL)

    title_match = re.search(r'^#\s+(.+)$', full_document, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "Summary Document"

    static_folder = config_data.get("static_folder", "tmp_imgs")
    os.makedirs(static_folder, exist_ok=True)

    file_name = f"doc_{generate_random_string(8)}"

    md_path = os.path.join(static_folder, file_name + ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(full_document)

    docx_path = os.path.join(static_folder, file_name + ".docx")
    try:
        _markdown_to_docx(full_document, docx_path)
    except Exception:
        docx_path = None

    pdf_path = os.path.join(static_folder, file_name + ".pdf")
    try:
        _markdown_to_pdf(full_document, pdf_path)
    except Exception:
        pdf_path = None

    static_url = config_data["static_path"].rstrip("/")
    static_folder = config_data.get("static_folder", "tmp_imgs")
    download_url_md = f"{static_url}/{static_folder}/{file_name}.md"
    download_url_docx = f"{static_url}/{static_folder}/{file_name}.docx" if docx_path else ""
    download_url_pdf = f"{static_url}/{static_folder}/{file_name}.pdf" if pdf_path else ""

    _finalize_event = {
        'phase': 'finalize', 'type': 'done',
        'content': full_document,
        'title': title,
        'file_name': file_name,
        'download_url_md': download_url_md,
        'download_url_docx': download_url_docx,
        'download_url_pdf': download_url_pdf,
    }

    record_report_generation(
        session_id=session_id,
        file_name=file_name,
        chat_history=json.dumps(conversation_history, ensure_ascii=False) if conversation_history else "",
        outline=json.dumps({"title": title}),
        full_text=full_document,
    )

    yield f"data: {json.dumps(_finalize_event, ensure_ascii=False)}\n\n"

    if yaml_base:
        _cleanup_workspace_files(yaml_base)

    record_session_operation(
        session_id, "/api/generate-document/finalize/",
        request_json, full_document[:5000], "",
        "success", f"Document finalized: {title}",
        prompt_length=0
    )


@router.post("/api/generate-document/finalize/")
async def finalize_document_api(request: Request, user_input: FinalizeInput):
    return StreamingResponse(
        _event_stream_finalize(
            user_input.markdown_content,
            user_input.session_id or "",
            user_input.model_dump_json(),
            yaml_base=user_input.yaml_base or "",
            conversation_history=user_input.conversation_history,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ── Doc workspace file management ────────────────────────────────────────


@router.get("/api/doc-workspace/files/")
async def list_workspace_files():
    try:
        files = os.listdir(DOC_WORKSPACE)
        yaml_files = sorted([f for f in files if f.endswith(".yaml")], reverse=True)
        result = []
        for f in yaml_files:
            path = os.path.join(DOC_WORKSPACE, f)
            mtime = os.path.getmtime(path)
            result.append({"name": f, "type": "yaml", "mtime": mtime})
        return JSONResponse(content={"files": result})
    except Exception as e:
        return JSONResponse(content={"files": [], "error": str(e)})


@router.get("/api/doc-workspace/file/{filename:path}")
async def read_workspace_file(filename: str):
    import re as _re
    if _re.search(r'[/\\]|\.\.', filename):
        return JSONResponse(content={"error": "Invalid filename"}, status_code=400)
    path = os.path.join(DOC_WORKSPACE, filename)
    if not os.path.isfile(path):
        return JSONResponse(content={"error": "File not found"}, status_code=404)
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return JSONResponse(content={"name": filename, "content": content})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@router.delete("/api/doc-workspace/yaml/{filename:path}")
async def delete_yaml_with_drafts(filename: str):
    import re as _re
    if _re.search(r'[/\\]|\.\.', filename):
        return JSONResponse(content={"error": "Invalid filename"}, status_code=400)
    if not filename.endswith(".yaml"):
        return JSONResponse(content={"error": "Not a YAML file"}, status_code=400)
    base = filename.replace("outline_", "").replace(".yaml", "")
    patterns = [
        f"outline_{base}.yaml",
        f"draft_{base}.md",
        f"draft_{base}_s*.md",
    ]
    deleted = []
    import glob
    for pattern in patterns:
        for f in glob.glob(os.path.join(DOC_WORKSPACE, pattern)):
            try:
                os.remove(f)
                deleted.append(os.path.basename(f))
            except Exception:
                pass
    return JSONResponse(content={"deleted": deleted})