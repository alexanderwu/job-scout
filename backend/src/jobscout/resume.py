"""Reading resume/profile text off disk (PLAN.md Phase 2: ``jobscout match
resume.pdf``).

Text extraction only — no structured parsing (sections, dates, skill
lists). The embedding model and the keyword-overlap explainability in
``matching.py`` both work directly on raw text, so there's nothing
downstream that needs a structured resume yet.
"""

from __future__ import annotations

from pathlib import Path


def read_resume_text(path: Path) -> str:
    """Extract plain text from a resume file.

    ``.pdf`` is parsed page by page; anything else is read as plain text
    (covers ``.txt``/``.md`` profiles, which are just as valid an input).
    """
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(encoding="utf-8")
