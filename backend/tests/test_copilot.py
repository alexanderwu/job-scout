"""Copilot features: deterministic cores + the LLM pass-through."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.copilot.cover_letter import draft_cover_letter
from jobscout.copilot.skill_gap import skill_gap
from jobscout.copilot.tailor import build_advice, tailor
from jobscout.llm import LLMProvider
from jobscout.matching.explain import extract_skills
from jobscout.models import Job

NOW = datetime.now(tz=UTC)


class FakeLLM(LLMProvider):
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate(self, prompt: str, *, system: str | None = None, max_tokens: int = 1024) -> str:
        self.calls.append({"prompt": prompt, "system": system, "max_tokens": max_tokens})
        return "LLM PROSE"


def job(**overrides: Any) -> Job:
    defaults: dict[str, Any] = {
        "id": 1,
        "title": "Data Engineer",
        "company": "Acme",
        "title_norm": "data engineer",
        "company_norm": "acme",
        "description": "Python, SQL, Airflow, and Kubernetes.",
        "first_seen": NOW,
        "last_seen": NOW,
    }
    return Job(**{**defaults, **overrides})


RESUME = "Engineer with Python and SQL, some Docker."


# --- tailoring ---------------------------------------------------------------


def test_tailor_core_separates_emphasis_from_gaps() -> None:
    advice = build_advice(job(), RESUME)

    assert "Python" in advice.emphasized_skills
    assert "Kubernetes" in advice.gap_skills
    joined = " ".join(advice.suggestions)
    assert "Lead with" in joined
    # The honesty guard: gap advice must be conditional, never "claim X".
    assert "Only if you genuinely have" in joined
    assert advice.prose is None  # no LLM -> no prose field


async def test_tailor_llm_only_rephrases() -> None:
    llm = FakeLLM()
    advice = await tailor(job(), RESUME, llm)

    assert advice.prose == "LLM PROSE"
    assert advice.suggestions  # deterministic core still present
    prompt = llm.calls[0]["prompt"]
    assert "Data Engineer" in prompt
    assert advice.suggestions[0] in prompt  # the LLM saw exactly our facts
    assert "never invent" in (llm.calls[0]["system"] or "").lower()


# --- cover letters -----------------------------------------------------------


async def test_template_letter_is_honest_scaffold() -> None:
    letter = await draft_cover_letter(job(), RESUME, None)

    assert letter.generated_by == "template"
    assert "Data Engineer" in letter.body
    assert "Acme" in letter.body
    assert "Python" in letter.body  # real shared skills filled in
    assert "[EDIT:" in letter.body  # human work is left visibly human


async def test_llm_letter_gets_resume_and_job_grounding() -> None:
    llm = FakeLLM()
    letter = await draft_cover_letter(job(), RESUME, llm)

    assert letter.generated_by == "fake"
    assert letter.body == "LLM PROSE"
    prompt = llm.calls[0]["prompt"]
    assert RESUME in prompt
    assert "Airflow" in prompt  # job description included
    system = llm.calls[0]["system"]
    assert system is not None
    assert "never invent" in system.lower()


# --- skill gap (against real DB) ---------------------------------------------


async def test_skill_gap_aggregates_role_demand(db_session: AsyncSession) -> None:
    descriptions = [
        "Python SQL Airflow",
        "Python Spark Kubernetes",
        "Python SQL dbt",
        "Figma only",  # different role, must not pollute the sample
    ]
    for i, description in enumerate(descriptions):
        title = "Data Engineer" if i < 3 else "Designer"
        db_session.add(
            Job(
                title=title,
                title_norm="data engineer" if i < 3 else "designer",
                company=f"C{i}",
                company_norm=f"c{i}",
                description=description,
                first_seen=NOW,
                last_seen=NOW,
            )
        )
    await db_session.commit()

    report = await skill_gap(db_session, "Data Engineer", extract_skills("I know Python and SQL"))

    assert report.sampled_jobs == 3
    have = {d.skill: d for d in report.have}
    missing = {d.skill: d for d in report.missing}
    assert have["Python"].count == 3  # every DE posting wants it...
    assert have["Python"].share == 1.0  # ...and the share says so
    assert "SQL" in have
    assert "Airflow" in missing  # demanded, not on the resume
    assert "Figma" not in have  # designer noise excluded...
    assert "Figma" not in missing  # ...from both buckets


async def test_skill_gap_empty_corpus(db_session: AsyncSession) -> None:
    report = await skill_gap(db_session, "Astronaut", set())
    assert report.sampled_jobs == 0
    assert report.have == []
    assert report.missing == []
