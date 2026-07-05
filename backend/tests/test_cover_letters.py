"""Cover-letter prompt-builder tests (PLAN.md Phase 4)."""

from __future__ import annotations

from jobscout.cover_letters import build_cover_letter_prompt


def test_prompt_includes_resume_and_job_fields() -> None:
    prompt = build_cover_letter_prompt(
        resume_text="Experienced Python engineer.",
        job_title="Senior Data Engineer",
        company="Acme Corp",
        job_description="Build data pipelines with Python and SQL.",
    )

    assert "Experienced Python engineer." in prompt
    assert "Senior Data Engineer" in prompt
    assert "Acme Corp" in prompt
    assert "Build data pipelines with Python and SQL." in prompt


def test_prompt_substitutes_placeholders_for_missing_company_and_description() -> None:
    prompt = build_cover_letter_prompt(
        resume_text="Experienced Python engineer.",
        job_title="Senior Data Engineer",
        company=None,
        job_description=None,
    )

    assert "None" not in prompt
    assert "the company" in prompt
    assert "(no description provided)" in prompt
