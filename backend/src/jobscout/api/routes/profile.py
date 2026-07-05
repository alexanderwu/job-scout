"""Resume upload and profile-status endpoints (PLAN.md Phase 3).

Uploading a resume replaces the one persisted ``Profile`` row (see
``models.Profile``) so the rest of the API — matches, feed — can rank
against it without the caller re-sending the resume every time.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.api.deps import get_embedding_provider, get_session
from jobscout.api.schemas import ProfileOut
from jobscout.embeddings.base import EmbeddingProvider
from jobscout.models import Profile
from jobscout.queries import get_profile, upsert_profile
from jobscout.resume import extract_resume_text

router = APIRouter(tags=["profile"])

_PREVIEW_LENGTH = 280


def _to_out(profile: Profile | None) -> ProfileOut:
    if profile is None:
        return ProfileOut(has_profile=False, updated_at=None, resume_preview=None)
    return ProfileOut(
        has_profile=True,
        updated_at=profile.updated_at,
        resume_preview=profile.resume_text[:_PREVIEW_LENGTH],
    )


@router.get("/profile", response_model=ProfileOut)
async def read_profile(session: AsyncSession = Depends(get_session)) -> ProfileOut:
    return _to_out(await get_profile(session))


@router.post("/profile", response_model=ProfileOut)
async def upload_profile(
    resume: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    provider: EmbeddingProvider = Depends(get_embedding_provider),
) -> ProfileOut:
    data = await resume.read()
    text = extract_resume_text(data, resume.filename or "resume.txt")
    (embedding,) = provider.embed([text])
    profile = await upsert_profile(
        session, resume_text=text, embedding=embedding, now=datetime.now(UTC)
    )
    await session.commit()
    return _to_out(profile)
