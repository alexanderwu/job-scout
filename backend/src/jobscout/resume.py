"""Reading resume/profile text (PLAN.md Phase 2: ``jobscout match
resume.pdf``; Phase 3: the same extraction from an API file upload).

Text extraction only — no structured parsing (sections, dates, skill
lists). The embedding model and the keyword-overlap explainability in
``matching.py`` both work directly on raw text, so there's nothing
downstream that needs a structured resume yet.
"""

from __future__ import annotations

import io
from pathlib import Path


def extract_resume_text(data: bytes, filename: str) -> str:
    """Extract plain text from resume file contents.

    ``.pdf`` is parsed page by page; anything else is decoded as plain
    text (covers ``.txt``/``.md`` profiles, which are just as valid an
    input). Dispatches on ``filename``'s suffix rather than sniffing
    content, matching ``read_resume_text``'s behavior for on-disk files.
    """
    if filename.lower().endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return data.decode("utf-8")


def read_resume_text(path: Path) -> str:
    """Extract plain text from a resume file on disk."""
    return extract_resume_text(path.read_bytes(), path.name)
