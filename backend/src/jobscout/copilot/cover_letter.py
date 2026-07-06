"""Cover-letter drafting.

Template mode (LLM_PROVIDER=none) produces a complete, honest skeleton:
real job/company/skill facts filled in, and [EDIT: ...] markers exactly
where only the human can speak (why this company, the anecdote behind a
skill). It is deliberately *not* pretending to be finished prose — a
template that looks done gets sent as-is, and generic letters read as
spam. The markers make the remaining work visible.

LLM mode drafts the whole letter, grounded in the resume and job
description, with instructions that keep it factual. This is the
feature PLAN.md predicted would justify a paid API: prose quality is
maximally user-visible here.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from jobscout.llm import LLMProvider
from jobscout.matching.embed_jobs import job_text
from jobscout.matching.explain import explain_match, extract_skills
from jobscout.models import Job

_SYSTEM = (
    "You write short, specific cover letters (220-300 words). Ground every "
    "claim in the provided resume; never invent employers, titles, metrics, "
    "or skills. Plain, direct tone — no 'I am writing to express', no "
    "buzzword chains. If the resume lacks something the job wants, do not "
    "pretend otherwise."
)


@dataclass
class CoverLetter:
    job_id: int
    body: str
    generated_by: str  # 'template' or the LLM provider name


def _template_letter(job: Job, resume_text: str) -> str:
    resume_skills = extract_skills(resume_text)
    explanation = explain_match(resume_skills, job_text(job))
    shared = ", ".join(explanation.overlapping[:5]) or "[EDIT: your most relevant skills]"
    company = job.company or "[EDIT: company name]"
    return f"""Dear {company} hiring team,

I'm applying for the {job.title} role. [EDIT: one sentence on why this
company specifically — a product you use, a problem they own, a post
that resonated.]

My background lines up with what the posting asks for: {shared}.
[EDIT: pick ONE of those skills and tell the concrete story — what you
built, the scale it ran at, what changed because of it.]

[EDIT: one sentence connecting your next step to this role — what you
want to build or get better at, and why this team is the place.]

I'd welcome the chance to talk about the role.

Best regards,
[EDIT: your name]"""


async def draft_cover_letter(job: Job, resume_text: str, llm: LLMProvider | None) -> CoverLetter:
    if llm is None:
        return CoverLetter(
            job_id=job.id, body=_template_letter(job, resume_text), generated_by="template"
        )
    prompt = (
        f"Write a cover letter for this job.\n\n"
        f"JOB TITLE: {job.title}\n"
        f"COMPANY: {job.company or 'unknown'}\n"
        f"JOB DESCRIPTION:\n{(job.description or '')[:4000]}\n\n"
        f"CANDIDATE RESUME:\n{resume_text[:4000]}"
    )
    body = await asyncio.to_thread(llm.generate, prompt, system=_SYSTEM, max_tokens=800)
    return CoverLetter(job_id=job.id, body=body, generated_by=llm.name)
