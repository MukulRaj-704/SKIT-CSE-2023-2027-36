"""
analyzer/services/text_extractor.py
===================================
Upload validation + text extraction for PDF and DOCX (no authentication, no
file is kept on disk: only extracted text and layout signals are stored).

PDF  -> PyMuPDF (already a dependency of the ``resume_parser`` engine)
DOCX -> standard library only (zipfile + ElementTree), so no new dependency
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePath
from xml.etree import ElementTree as ET

from .. import config
from ..exceptions import ExtractionError

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


@dataclass
class ExtractedDocument:
    text: str
    file_type: str  # "pdf" | "docx"
    page_count: int = 1
    links: list = field(default_factory=list)
    layout: dict = field(default_factory=dict)  # signals for the formatting analyzer


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_upload(filename: str, data: bytes) -> str:
    """Return the file type or raise ``ExtractionError`` (HTTP 400)."""
    ext = PurePath(filename or "").suffix.lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        raise ExtractionError(
            "unsupported_format",
            f"Unsupported file format '{ext or 'unknown'}'. Upload a PDF or DOCX resume.",
        )
    if not data:
        raise ExtractionError("empty_file", "The uploaded file is empty.")
    limit = config.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(data) > limit:
        raise ExtractionError(
            "file_too_large", f"Resumes must be {config.MAX_UPLOAD_SIZE_MB} MB or smaller."
        )
    if ext == ".pdf" and not data.lstrip()[:5].startswith(b"%PDF"):
        raise ExtractionError("corrupted_file", "This file is not a valid PDF (corrupted or renamed).")
    if ext == ".docx" and not data[:2] == b"PK":
        raise ExtractionError("corrupted_file", "This file is not a valid DOCX (corrupted or renamed).")
    return ext.lstrip(".")


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def _pdf_columns(blocks, page_width) -> bool:
    """Detectable multi-column layout: two well-filled text columns side by side."""
    text_blocks = [b for b in blocks if len((b[4] or "").strip()) > 20]
    if len(text_blocks) < 6 or not page_width:
        return False
    mid = page_width / 2
    left = [b for b in text_blocks if b[2] <= mid * 1.08]
    right = [b for b in text_blocks if b[0] >= mid * 0.92]
    if len(left) < 3 or len(right) < 3:
        return False
    chars = lambda bs: sum(len(b[4]) for b in bs)
    total = chars(text_blocks)
    # Both columns carry real content and they share vertical space.
    overlap = min(max(b[3] for b in left), max(b[3] for b in right)) - max(
        min(b[1] for b in left), min(b[1] for b in right)
    )
    return chars(left) / total > 0.2 and chars(right) / total > 0.2 and overlap > 100


def _extract_pdf(data: bytes) -> ExtractedDocument:
    try:
        import pymupdf
    except Exception as exc:  # pragma: no cover - environment dependent
        from ..exceptions import EngineUnavailable

        raise EngineUnavailable("PDF support needs PyMuPDF (`pip install pymupdf`).") from exc

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ExtractionError("corrupted_file", "The PDF could not be opened (corrupted file).") from exc

    try:
        if doc.needs_pass:
            raise ExtractionError("encrypted_file", "The PDF is password protected.")
        pages, links, images, two_col = [], [], 0, False
        for page in doc:
            pages.append(page.get_text("text", sort=True))
            images += len(page.get_images())
            for link in page.get_links():
                if link.get("uri"):
                    links.append(link["uri"])
            two_col = two_col or _pdf_columns(page.get_text("blocks"), page.rect.width)
        page_count = len(doc)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError("corrupted_file", "The PDF could not be read (corrupted file).") from exc
    finally:
        doc.close()

    text = "\n".join(pages)
    if len(text.strip()) < config.MIN_RESUME_CHARS and images:
        raise ExtractionError(
            "scanned_pdf",
            "No selectable text found. This looks like a scanned or image-only PDF; "
            "export your resume as a text-based PDF or upload a DOCX.",
            status=422,
        )
    return ExtractedDocument(
        text=text,
        file_type="pdf",
        page_count=page_count,
        links=links,
        layout={"multi_column": two_col, "images": images, "tables": 0},
    )


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------


def _para_text(p) -> str:
    parts = []
    for node in p.iter():
        if node.tag == _W + "t":
            parts.append(node.text or "")
        elif node.tag == _W + "tab":
            parts.append("   ")
        elif node.tag in (_W + "br", _W + "cr"):
            parts.append("\n")
    return "".join(parts)


def _extract_docx(data: bytes) -> ExtractedDocument:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        xml = zf.read("word/document.xml")
        root = ET.fromstring(xml)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise ExtractionError("corrupted_file", "The DOCX could not be opened (corrupted file).") from exc

    links = []
    try:
        rels = ET.fromstring(zf.read("word/_rels/document.xml.rels"))
        links = [
            r.get("Target")
            for r in rels
            if r.get("Type", "").endswith("/hyperlink") and r.get("Target", "").startswith(("http", "mailto"))
        ]
    except (KeyError, ET.ParseError):
        pass

    body = root.find(_W + "body")
    lines, tables = [], 0

    def walk(parent):
        nonlocal tables
        for child in parent:
            if child.tag == _W + "p":
                lines.append(_para_text(child))
            elif child.tag == _W + "tbl":
                tables += 1
                for row in child.iter(_W + "tr"):
                    cells = [
                        " ".join(_para_text(p) for p in cell.iter(_W + "p")).strip()
                        for cell in row.findall(_W + "tc")
                    ]
                    lines.append("   ".join(c for c in cells if c))
            elif child.tag in (_W + "sdt", _W + "sdtContent"):
                walk(child)

    if body is not None:
        walk(body)

    text = "\n".join(lines)
    images = len(list(root.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip")))
    textboxes = len(list(root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}txbxContent")))
    cols = any(
        int(c.get(_W + "num", "1")) > 1 for c in root.iter(_W + "cols") if c.get(_W + "num", "1").isdigit()
    )
    # Page count is not stored in DOCX: estimate from word count (~500 words/page).
    pages = max(1, round(len(text.split()) / 500)) if text.strip() else 1
    return ExtractedDocument(
        text=text,
        file_type="docx",
        page_count=pages,
        links=links,
        layout={"multi_column": cols, "images": images, "tables": tables, "text_boxes": textboxes},
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_document(filename: str, data: bytes) -> ExtractedDocument:
    """Validate and extract. Raises ``ExtractionError`` with a user-facing message."""
    file_type = validate_upload(filename, data)
    doc = _extract_pdf(data) if file_type == "pdf" else _extract_docx(data)

    text = re.sub(r"\r\n?", "\n", doc.text)
    if len(text.strip()) < config.MIN_RESUME_CHARS:
        raise ExtractionError(
            "no_text",
            "Could not extract enough text from this resume. If it is a scanned image, "
            "export a text-based PDF or upload a DOCX.",
            status=422,
        )
    if len(text) > config.MAX_RESUME_CHARS:
        raise ExtractionError("too_long", "This document is far too long to be a resume.")
    doc.text = text
    return doc
