"""Resume-tailoring suggestions for one specific job.

The deterministic core produces *typed* suggestions (emphasize /
add-if-true / mirror-language), each traceable to evidence: a skill
both sides mention, a skill only the job mentions, a phrase worth
mirroring. The optional LLM pass rewrites those bullets into flowing
advice but can neither add nor remove claims — the honesty boundary
lives in the deterministic layer, where it's enforceable.

(That's also why the add-if-true wording is so careful: a tailoring
tool that says "claim Kubernetes experience" is a liability. Ours says
"the job wants Kubernetes and your resume doesn't mention it — add it
only if you actually have it".)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from jobscout.llm import LLMProvider
from jobscout.matching.embed_jobs import job_text
from jobscout.matching.explain import explain_match, extract_skills
from jobscout.models import Job

_SYSTEM = (
    "You are a resume coach. Rewrite the provided factual suggestions as "
    "clear, encouraging advice. Never invent skills or experience that are "
    "not in the suggestions; never advise claiming something the candidate "
    "may not have."
)


@dataclass
class TailoringAdvice:
    job_id: int
    suggestions: list[str] = field(default_factory=list)
    emphasized_skills: list[str] = field(default_factory=list)
    gap_skills: list[str] = field(default_factory=list)
    prose: str | None = None  # LLM-phrased version, when a provider is configured


def build_advice(job: Job, resume_text: str) -> TailoringAdvice:
    resume_skills = extract_skills(resume_text)
    explanation = explain_match(resume_skills, job_text(job))
    advice = TailoringAdvice(
        job_id=job.id,
        emphasized_skills=explanation.overlapping,
        gap_skills=explanation.missing,
    )

    if explanation.overlapping:
        skills = ", ".join(explanation.overlapping[:6])
        advice.suggestions.append(
            f"Lead with your {skills} experience — this posting asks for those "
            "directly, so move them above the fold and attach concrete outcomes "
            "(scale, latency, revenue, team size)."
        )
    if explanation.missing:
        skills = ", ".join(explanation.missing[:6])
        advice.suggestions.append(
            f"The posting also wants: {skills}. Only if you genuinely have any "
            "of these, name them explicitly — matching the posting's own "
            "vocabulary helps both recruiters and screening software."
        )
    if job.title:
        advice.suggestions.append(
            f"Mirror the role framing: if your current headline differs, consider "
            f'echoing "{job.title}" phrasing where it\'s truthful, so the first '
            "line reads as an obvious fit."
        )
    if not advice.suggestions:  # pragma: no cover - job with no text at all
        advice.suggestions.append(
            "Not enough job-description text to tailor against — open the "
            "original posting and compare manually."
        )
    return advice


async def tailor(job: Job, resume_text: str, llm: LLMProvider | None) -> TailoringAdvice:
    advice = build_advice(job, resume_text)
    if llm is not None:
        prompt = (
            f"Job: {job.title} at {job.company or 'unknown company'}.\n"
            "Suggestions to rephrase (keep every factual constraint):\n- "
            + "\n- ".join(advice.suggestions)
        )
        advice.prose = await asyncio.to_thread(llm.generate, prompt, system=_SYSTEM, max_tokens=600)
    return advice
