"""Profile endpoints: upload a resume, get matches, poll the feed.

The upload endpoint accepts either a file (PDF/txt/md, multipart) or
raw pasted text — the two ways people actually have a resume at hand.
Uploaded bytes go to a temp file and through the same
``load_resume_text`` the CLI uses; one parsing path to maintain.
"""

from __future__ import annotations

import asyncio
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select

from jobscout.api.deps import ProviderDep, SessionDep
from jobscout.api.schemas import FeedResponse, MatchResponse, ProfileOut
from jobscout.api.serialize import to_match_response
from jobscout.matching.engine import MatchFilters, rank_jobs
from jobscout.matching.explain import extract_skills
from jobscout.matching.resume import ResumeReadError, load_resume_text
from jobscout.models import Profile

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.post("", status_code=201)
async def create_profile(
    session: SessionDep,
    provider: ProviderDep,
    name: Annotated[str, Form()] = "default",
    file: Annotated[UploadFile | None, File()] = None,
    text: Annotated[str | None, Form()] = None,
) -> ProfileOut:
    if file is not None:
        suffix = Path(file.filename or "resume.pdf").suffix or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = Path(tmp.name)
        try:
            resume_text = load_resume_text(tmp_path)
        except ResumeReadError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            tmp_path.unlink(missing_ok=True)
    elif text and text.strip():
        resume_text = text.strip()
    else:
        raise HTTPException(status_code=422, detail="provide a resume file or pasted text")

    (embedding,) = await asyncio.to_thread(provider.embed, [resume_text])
    now = datetime.now(tz=UTC)
    profile = Profile(
        name=name,
        resume_text=resume_text,
        embedding=embedding,
        embedding_sig=provider.signature,
        created_at=now,
        updated_at=now,
    )
    session.add(profile)
    await session.flush()
    return _profile_out(profile)


@router.get("")
async def list_profiles(session: SessionDep) -> list[ProfileOut]:
    profiles = (await session.scalars(select(Profile).order_by(Profile.id))).all()
    return [_profile_out(p) for p in profiles]


@router.get("/{profile_id}")
async def get_profile(profile_id: int, session: SessionDep) -> ProfileOut:
    return _profile_out(await _load(session, profile_id))


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(profile_id: int, session: SessionDep) -> None:
    profile = await _load(session, profile_id)
    await session.delete(profile)


@router.post("/{profile_id}/match")
async def match_profile(
    profile_id: int,
    session: SessionDep,
    provider: ProviderDep,
    limit: int = Query(20, le=100),
    location: str | None = None,
    remote_only: bool = False,
    min_salary: int | None = None,
    max_age_days: int = 45,
) -> MatchResponse:
    """Ranked matches for a stored profile — the UI's main screen."""
    profile = await _load(session, profile_id)
    query_vec = await _current_vector(session, provider, profile)
    result = await rank_jobs(
        session,
        provider,
        query_vec,
        extract_skills(profile.resume_text),
        filters=MatchFilters(
            location_contains=location,
            remote_only=remote_only,
            min_salary=min_salary,
            max_age_days=max_age_days,
        ),
        limit=limit,
    )
    return to_match_response(result)


@router.get("/{profile_id}/feed")
async def feed(
    profile_id: int,
    session: SessionDep,
    provider: ProviderDep,
    hours: int = Query(24, description="Jobs first seen within this window."),
    limit: int = Query(20, le=100),
) -> FeedResponse:
    """New-since-`hours` jobs ranked for this profile.

    Polled by the frontend (PLAN.md offered WebSocket or polling —
    with ingestion running every ~30 minutes, a poll is operationally
    free and push infrastructure would notify faster than the data
    actually changes).
    """
    profile = await _load(session, profile_id)
    query_vec = await _current_vector(session, provider, profile)
    since = datetime.now(tz=UTC) - timedelta(hours=hours)
    result = await rank_jobs(
        session,
        provider,
        query_vec,
        extract_skills(profile.resume_text),
        limit=limit,
        first_seen_after=since,
    )
    return FeedResponse(since=since, matches=to_match_response(result).matches)


async def _load(session: SessionDep, profile_id: int) -> Profile:
    profile = await session.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not found")
    return profile


async def _current_vector(
    session: SessionDep, provider: ProviderDep, profile: Profile
) -> list[float]:
    """The profile's vector in the *current* embedding space.

    Profiles created before a model switch hold stale-signature
    vectors; instead of failing (or worse, silently comparing across
    spaces), re-embed from the stored resume text and persist — the
    same self-healing rule the job corpus follows in embed_jobs.py.
    """
    if profile.embedding is not None and profile.embedding_sig == provider.signature:
        return list(profile.embedding)
    (vector,) = await asyncio.to_thread(provider.embed, [profile.resume_text])
    profile.embedding = vector
    profile.embedding_sig = provider.signature
    profile.updated_at = datetime.now(tz=UTC)
    await session.flush()
    return vector


def _profile_out(profile: Profile) -> ProfileOut:
    out = ProfileOut.model_validate(profile)
    out.skills = sorted(extract_skills(profile.resume_text))
    return out
