"""Resume loading: text, markdown, PDF, and the failure modes."""

from pathlib import Path

import pytest

from jobscout.matching.resume import ResumeReadError, load_resume_text


def mini_pdf(text: str) -> bytes:
    """Assemble a minimal valid one-page PDF containing `text`.

    Built here, byte by byte, instead of committing a binary fixture or
    adding a PDF-writing dev dependency: a PDF is just numbered objects
    plus an xref table of their byte offsets, and pypdf's reader needs
    that table to be present and correct — so we compute it.
    """
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for num, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (num, body)
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Root 1 0 R /Size %d >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_at,
    )
    return bytes(out)


def test_reads_txt_and_md(tmp_path: Path) -> None:
    txt = tmp_path / "resume.txt"
    txt.write_text("Python engineer.\n")
    assert load_resume_text(txt) == "Python engineer."

    md = tmp_path / "resume.md"
    md.write_text("# Me\nPython engineer.\n")
    assert "Python engineer." in load_resume_text(md)


def test_reads_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(mini_pdf("Python SQL Airflow engineer"))
    assert "Python SQL Airflow engineer" in load_resume_text(pdf)


def test_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_resume_text(Path("/nonexistent/resume.pdf"))


def test_unsupported_format_raises(tmp_path: Path) -> None:
    docx = tmp_path / "resume.docx"
    docx.write_bytes(b"not really")
    with pytest.raises(ResumeReadError, match="unsupported"):
        load_resume_text(docx)


def test_empty_extraction_raises_helpfully(tmp_path: Path) -> None:
    empty = tmp_path / "resume.txt"
    empty.write_text("   \n")
    with pytest.raises(ResumeReadError, match="scanned"):
        load_resume_text(empty)
