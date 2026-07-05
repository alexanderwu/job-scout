"""Cover-letter prompt construction (PLAN.md Phase 4).

Pure text-building logic, kept separate from ``jobscout.llm`` (no
HTTP/ABC dependency here) the same way ``matching.py`` sits alongside
``jobscout.embeddings`` — fully unit-testable without a DB or network.
"""

from __future__ import annotations


def build_cover_letter_prompt(
    *,
    resume_text: str,
    job_title: str,
    company: str | None,
    job_description: str | None,
) -> str:
    """Build the prompt an ``LLMProvider`` drafts a cover letter from."""
    return (
        "Write a cover letter for the job below, based on the candidate's resume.\n\n"
        "Rules:\n"
        "- 3-4 paragraphs, no letterhead or date.\n"
        "- Reference specific overlap between the resume and the job description.\n"
        "- Never invent experience, skills, or credentials not present in the resume.\n"
        "- Plain prose only, no markdown formatting.\n\n"
        f"Job title: {job_title}\n"
        f"Company: {company or 'the company'}\n"
        f"Job description:\n{job_description or '(no description provided)'}\n\n"
        f"Resume:\n{resume_text}\n"
    )
