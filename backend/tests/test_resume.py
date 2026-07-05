"""Resume text extraction tests (PLAN.md Phase 2: ``jobscout match resume.pdf``)."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfWriter

from jobscout.resume import read_resume_text


def test_reads_plain_text_file(tmp_path: Path) -> None:
    path = tmp_path / "resume.txt"
    path.write_text("Senior Data Engineer, Python, SQL.", encoding="utf-8")
    assert read_resume_text(path) == "Senior Data Engineer, Python, SQL."


def test_reads_markdown_file_as_plain_text(tmp_path: Path) -> None:
    path = tmp_path / "resume.md"
    path.write_text("# Resume\n\nPython engineer.", encoding="utf-8")
    assert read_resume_text(path) == "# Resume\n\nPython engineer."


def test_reads_pdf_file_without_crashing(tmp_path: Path) -> None:
    path = tmp_path / "resume.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with path.open("wb") as f:
        writer.write(f)

    # A blank page has no text to extract; the important thing is that a
    # real .pdf is routed through the PDF parser instead of being read as
    # raw bytes/text.
    assert read_resume_text(path) == ""
