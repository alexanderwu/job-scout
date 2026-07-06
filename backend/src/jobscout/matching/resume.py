"""Load a resume/profile into plain text.

Accepts PDF (what people actually have), plus .txt/.md (what's nicest
to keep in version control — a plain-text "profile" you edit as your
search evolves works better with this tool than re-exporting a PDF).

pypdf over pdfminer/PyMuPDF: pure Python, tiny, and resume-grade PDFs
(digital text, simple layout) are its easy case. If a resume comes back
empty — usually a scanned image — we say so explicitly rather than
matching against an empty string, which would "work" and return
garbage rankings.
"""

from __future__ import annotations

from pathlib import Path


class ResumeReadError(ValueError):
    """The file exists but produced no usable text."""


def load_resume_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = _pdf_text(path)
    elif suffix in {".txt", ".md", ""}:
        text = path.read_text(encoding="utf-8", errors="replace")
    else:
        raise ResumeReadError(f"unsupported resume format {suffix!r} — use .pdf, .txt, or .md")
    text = text.strip()
    if not text:
        raise ResumeReadError(
            f"no text could be extracted from {path.name}. If this is a "
            "scanned/image PDF, export a text-based PDF or paste the text "
            "into a .txt file instead."
        )
    return text


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)
