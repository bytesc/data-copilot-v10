import io
import re

import docx
import PyPDF2
from fastapi import HTTPException


# Compound File Binary Format signature (legacy Word 97-2003 binary .doc).
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
# ZIP local-file-header signature: an OOXML .docx renamed to .doc still starts
# with this, so it can be routed to the .docx parser.
_ZIP_MAGIC = b"PK\x03\x04"


def _decode_text_bytes(file_content: bytes) -> str:
    """Decode text bytes tolerating a UTF-8 BOM and common CN encodings.

    A single ``file_content.decode('utf-8')`` previously raised
    ``UnicodeDecodeError`` on non-UTF-8 files (e.g. GBK), which the upload
    handler turned into an opaque 500. ``latin-1`` never fails, so this always
    returns a string.
    """
    for encoding in ("utf-8-sig", "gb18030", "latin-1"):
        try:
            return file_content.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return file_content.decode("utf-8", errors="replace")


def extract_text_from_txt(file_content: bytes) -> str:
    return _decode_text_bytes(file_content)


def extract_text_from_docx(file_content: bytes) -> str:
    file_stream = io.BytesIO(file_content)
    try:
        doc = docx.Document(file_stream)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid or unreadable .docx document: {e}",
        )
    text = []
    for paragraph in doc.paragraphs:
        text.append(paragraph.text)
    return '\n'.join(text)


def extract_text_from_pdf(file_content: bytes) -> str:
    file_stream = io.BytesIO(file_content)
    try:
        pdf_reader = PyPDF2.PdfReader(file_stream)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid or unreadable PDF file: {e}",
        )
    text = []
    for page in pdf_reader.pages:
        try:
            page_text = page.extract_text()
        except Exception:
            page_text = None
        # Pages without a text layer (e.g. scanned images) make extract_text()
        # return None; '\n'.join(...) used to raise TypeError and fail the whole
        # upload. Treat a missing text layer as an empty page instead.
        if page_text:
            text.append(page_text)
    result = '\n'.join(text)
    if not result.strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "No extractable text found in the PDF (it may be a "
                "scanned/image-only document)."
            ),
        )
    return result


def _strip_rtf(raw: bytes) -> str:
    """Best-effort RTF text extraction without extra dependencies."""
    text = raw.decode("latin-1", errors="ignore")
    # Drop destination groups such as {\*\generator ...}.
    text = re.sub(r"\{\\\*.*?\}", "", text, flags=re.DOTALL)

    def _hex(match):
        try:
            return bytes([int(match.group(1), 16)]).decode("latin-1")
        except ValueError:
            return ""

    text = re.sub(r"\\'([0-9a-fA-F]{2})", _hex, text)
    # Paragraph/line/section breaks become newlines before generic removal.
    text = re.sub(r"\\(par|line|sect)\b", "\n", text)
    # Remove remaining control words (e.g. \b, \fs24, \pard).
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", text)
    # Unescape literal braces/backslashes, then drop group delimiters.
    text = text.replace("\\{", "{").replace("\\}", "}").replace("\\\\", "\\")
    text = text.replace("{", "").replace("}", "")
    return text.strip()


def extract_text_from_doc(file_content: bytes) -> str:
    """Extract text from a ``.doc`` upload.

    A ``.doc`` file is not always the legacy binary format: it may be an OOXML
    ``.docx`` or an RTF document renamed to ``.doc``. The legacy binary (OLE2)
    format cannot be parsed reliably without a dedicated library, and the
    previous implementation decoded those bytes as UTF-8, silently sending
    garbage text to the model. This detects the real format, handles the cases
    that can be handled, and fails with a clear 400 for the binary format
    instead of returning garbage.
    """
    if file_content.startswith(_OLE2_MAGIC):
        raise HTTPException(
            status_code=400,
            detail=(
                "Legacy binary .doc files are not supported. Please re-save "
                "the document as .docx or .pdf and upload again."
            ),
        )
    if file_content.startswith(_ZIP_MAGIC):
        # OOXML document renamed to .doc.
        return extract_text_from_docx(file_content)
    if file_content[:5] == b"{\\rtf":
        return _strip_rtf(file_content)
    return _decode_text_bytes(file_content)


def process_file_content(file_content: bytes, file_extension: str) -> str:
    file_extension = file_extension.lower()
    if file_extension == '.txt':
        return extract_text_from_txt(file_content)
    elif file_extension == '.docx':
        return extract_text_from_docx(file_content)
    elif file_extension == '.doc':
        return extract_text_from_doc(file_content)
    elif file_extension == '.pdf':
        return extract_text_from_pdf(file_content)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_extension}")
