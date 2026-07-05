from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.embeddings.base import EMBEDDING_DIM
from jobscout.models import Job
from jobscout.queries import (
    delete_saved_job,
    get_cover_letter,
    get_profile,
    get_saved_job,
    jobs_first_seen_between,
    jobs_first_seen_since,
    jobs_matching_role,
    jobs_missing_embeddings,
    jobs_with_embeddings,
    jobs_with_salary,
    list_due_reminders,
    list_saved_jobs,
    search_jobs,
    upsert_cover_letter,
    upsert_profile,
    upsert_saved_job_status,
    upsert_saved_job_tracking,
)


def make_embedding(seed: float) -> list[float]:
    return [seed] + [0.0] * (EMBEDDING_DIM - 1)


def make_job(**overrides: object) -> Job:
    defaults: dict[str, object] = {
        "normalized_title": "data engineer",
        "normalized_company": "acme corp",
        "canonical_url": "https://example.com/1",
        "title": "Data Engineer",
        "company": "Acme Corp",
        "location": None,
        "posted_at": None,
        "first_seen": datetime(2026, 1, 1, tzinfo=UTC),
        "last_seen": datetime(2026, 1, 1, tzinfo=UTC),
    }
    return Job(**{**defaults, **overrides})


async def test_jobs_first_seen_since_filters_and_orders(session: AsyncSession) -> None:
    old = make_job(
        canonical_url="https://example.com/old", first_seen=datetime(2025, 1, 1, tzinfo=UTC)
    )
    recent = make_job(
        canonical_url="https://example.com/recent", first_seen=datetime(2026, 6, 1, tzinfo=UTC)
    )
    newest = make_job(
        canonical_url="https://example.com/newest", first_seen=datetime(2026, 6, 15, tzinfo=UTC)
    )
    session.add_all([old, recent, newest])
    await session.commit()

    result = await jobs_first_seen_since(session, since=datetime(2026, 1, 1, tzinfo=UTC))

    assert [job.canonical_url for job in result] == [
        "https://example.com/newest",
        "https://example.com/recent",
    ]


async def test_jobs_missing_embeddings_excludes_embedded_and_description_less_jobs(
    session: AsyncSession,
) -> None:
    no_description = make_job(canonical_url="https://example.com/1", description=None)
    pending = make_job(
        canonical_url="https://example.com/2", description="Build things.", embedding=None
    )
    already_embedded = make_job(
        canonical_url="https://example.com/3",
        description="Build other things.",
        embedding=make_embedding(0.1),
    )
    session.add_all([no_description, pending, already_embedded])
    await session.commit()

    result = await jobs_missing_embeddings(session)

    assert [job.canonical_url for job in result] == ["https://example.com/2"]


async def test_jobs_with_embeddings_filters_by_location(session: AsyncSession) -> None:
    sf_job = make_job(
        canonical_url="https://example.com/sf",
        location="San Francisco, CA",
        embedding=make_embedding(0.1),
    )
    ny_job = make_job(
        canonical_url="https://example.com/ny",
        location="New York, NY",
        embedding=make_embedding(0.3),
    )
    unembedded = make_job(canonical_url="https://example.com/none", embedding=None)
    session.add_all([sf_job, ny_job, unembedded])
    await session.commit()

    all_embedded = await jobs_with_embeddings(session)
    assert {job.canonical_url for job in all_embedded} == {
        "https://example.com/sf",
        "https://example.com/ny",
    }

    sf_only = await jobs_with_embeddings(session, location="San Francisco")
    assert [job.canonical_url for job in sf_only] == ["https://example.com/sf"]


async def test_search_jobs_orders_by_first_seen_desc_and_paginates(session: AsyncSession) -> None:
    old = make_job(
        canonical_url="https://example.com/old", first_seen=datetime(2026, 1, 1, tzinfo=UTC)
    )
    mid = make_job(
        canonical_url="https://example.com/mid", first_seen=datetime(2026, 2, 1, tzinfo=UTC)
    )
    new = make_job(
        canonical_url="https://example.com/new", first_seen=datetime(2026, 3, 1, tzinfo=UTC)
    )
    session.add_all([old, mid, new])
    await session.commit()

    page1 = await search_jobs(session, limit=2)
    assert [job.canonical_url for job in page1] == [
        "https://example.com/new",
        "https://example.com/mid",
    ]

    page2 = await search_jobs(session, limit=2, offset=2)
    assert [job.canonical_url for job in page2] == ["https://example.com/old"]


async def test_search_jobs_filters_by_location(session: AsyncSession) -> None:
    sf_job = make_job(canonical_url="https://example.com/sf", location="San Francisco, CA")
    ny_job = make_job(canonical_url="https://example.com/ny", location="New York, NY")
    session.add_all([sf_job, ny_job])
    await session.commit()

    result = await search_jobs(session, location="San Francisco")
    assert [job.canonical_url for job in result] == ["https://example.com/sf"]


async def test_upsert_profile_creates_then_replaces_the_single_row(session: AsyncSession) -> None:
    assert await get_profile(session) is None

    created = await upsert_profile(
        session,
        resume_text="Python engineer.",
        embedding=make_embedding(0.1),
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    await session.commit()
    assert created.resume_text == "Python engineer."

    updated = await upsert_profile(
        session,
        resume_text="Python and Go engineer.",
        embedding=make_embedding(0.2),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    await session.commit()

    assert updated.id == created.id
    fetched = await get_profile(session)
    assert fetched is not None
    assert fetched.resume_text == "Python and Go engineer."


async def test_saved_job_lifecycle(session: AsyncSession) -> None:
    job = make_job(canonical_url="https://example.com/1")
    session.add(job)
    await session.commit()

    assert await get_saved_job(session, job.id) is None

    saved = await upsert_saved_job_status(
        session, job.id, "saved", now=datetime(2026, 1, 1, tzinfo=UTC)
    )
    await session.commit()
    assert saved.status == "saved"

    updated = await upsert_saved_job_status(
        session, job.id, "applied", now=datetime(2026, 1, 2, tzinfo=UTC)
    )
    await session.commit()
    assert updated.id == saved.id
    assert updated.status == "applied"

    listed = await list_saved_jobs(session)
    assert [s.job_id for s in listed] == [job.id]
    assert listed[0].job.canonical_url == "https://example.com/1"

    assert await delete_saved_job(session, job.id) is True
    assert await get_saved_job(session, job.id) is None
    assert await delete_saved_job(session, job.id) is False


async def test_upsert_saved_job_status_stamps_transition_timestamps(session: AsyncSession) -> None:
    job = make_job(canonical_url="https://example.com/1")
    session.add(job)
    await session.commit()

    applied = await upsert_saved_job_status(
        session, job.id, "applied", now=datetime(2026, 1, 2, tzinfo=UTC)
    )
    await session.commit()
    assert applied.applied_at == datetime(2026, 1, 2, tzinfo=UTC)
    assert applied.interviewing_at is None

    interviewing = await upsert_saved_job_status(
        session, job.id, "interviewing", now=datetime(2026, 1, 3, tzinfo=UTC)
    )
    await session.commit()
    # The earlier transition's timestamp is untouched by a later one.
    assert interviewing.applied_at == datetime(2026, 1, 2, tzinfo=UTC)
    assert interviewing.interviewing_at == datetime(2026, 1, 3, tzinfo=UTC)


async def test_upsert_saved_job_status_does_not_restamp_on_reentry(session: AsyncSession) -> None:
    """Re-entering a status (e.g. reapplying after a rejection) must not
    overwrite the original timestamp for that status — the timeline
    should preserve the first time each state was reached."""
    job = make_job(canonical_url="https://example.com/1")
    session.add(job)
    await session.commit()

    await upsert_saved_job_status(session, job.id, "applied", now=datetime(2026, 1, 2, tzinfo=UTC))
    await session.commit()
    await upsert_saved_job_status(session, job.id, "rejected", now=datetime(2026, 1, 3, tzinfo=UTC))
    await session.commit()
    reapplied = await upsert_saved_job_status(
        session, job.id, "applied", now=datetime(2026, 2, 1, tzinfo=UTC)
    )
    await session.commit()

    # sqlite (unlike Postgres) doesn't reliably round-trip tzinfo across a
    # re-fetched row, so compare naively here — the point under test is
    # the *value*, which the guard preserved instead of restamping.
    assert reapplied.applied_at is not None
    assert reapplied.rejected_at is not None
    assert reapplied.applied_at.replace(tzinfo=None) == datetime(2026, 1, 2)
    assert reapplied.rejected_at.replace(tzinfo=None) == datetime(2026, 1, 3)


async def test_upsert_saved_job_tracking_sets_reminder_and_notes(session: AsyncSession) -> None:
    job = make_job(canonical_url="https://example.com/1")
    session.add(job)
    await session.commit()

    assert (
        await upsert_saved_job_tracking(
            session, job.id, reminder_at=datetime(2026, 2, 1, tzinfo=UTC), notes="Follow up"
        )
        is None
    )

    await upsert_saved_job_status(session, job.id, "saved", now=datetime(2026, 1, 1, tzinfo=UTC))
    await session.commit()

    updated = await upsert_saved_job_tracking(
        session, job.id, reminder_at=datetime(2026, 2, 1, tzinfo=UTC), notes="Follow up"
    )
    await session.commit()
    assert updated is not None
    assert updated.reminder_at == datetime(2026, 2, 1, tzinfo=UTC)
    assert updated.notes == "Follow up"


async def test_list_due_reminders_filters_and_orders_by_reminder_at(session: AsyncSession) -> None:
    soon = make_job(canonical_url="https://example.com/soon")
    later = make_job(canonical_url="https://example.com/later")
    no_reminder = make_job(canonical_url="https://example.com/none")
    session.add_all([soon, later, no_reminder])
    await session.commit()

    for job in (soon, later, no_reminder):
        await upsert_saved_job_status(
            session, job.id, "saved", now=datetime(2026, 1, 1, tzinfo=UTC)
        )
    await session.commit()

    await upsert_saved_job_tracking(
        session, later.id, reminder_at=datetime(2026, 3, 1, tzinfo=UTC), notes=None
    )
    await upsert_saved_job_tracking(
        session, soon.id, reminder_at=datetime(2026, 2, 1, tzinfo=UTC), notes=None
    )
    await session.commit()

    due = await list_due_reminders(session, before=datetime(2026, 6, 1, tzinfo=UTC))
    assert [r.job_id for r in due] == [soon.id, later.id]

    only_soon = await list_due_reminders(session, before=datetime(2026, 2, 15, tzinfo=UTC))
    assert [r.job_id for r in only_soon] == [soon.id]


async def test_cover_letter_upsert_creates_then_overwrites_content(session: AsyncSession) -> None:
    job = make_job(canonical_url="https://example.com/1")
    session.add(job)
    await session.commit()

    assert await get_cover_letter(session, job.id) is None

    created = await upsert_cover_letter(
        session, job_id=job.id, content="Draft one.", now=datetime(2026, 1, 1, tzinfo=UTC)
    )
    await session.commit()
    assert created.content == "Draft one."

    updated = await upsert_cover_letter(
        session, job_id=job.id, content="Draft two.", now=datetime(2026, 1, 2, tzinfo=UTC)
    )
    await session.commit()

    assert updated.id == created.id
    assert updated.content == "Draft two."
    assert updated.created_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert updated.updated_at == datetime(2026, 1, 2, tzinfo=UTC)


async def test_jobs_matching_role_filters_by_title_substring_case_insensitively(
    session: AsyncSession,
) -> None:
    engineer = make_job(
        canonical_url="https://example.com/1",
        title="Senior Data Engineer",
        description="Build pipelines.",
    )
    manager = make_job(
        canonical_url="https://example.com/2", title="Product Manager", description="Ship things."
    )
    no_description = make_job(
        canonical_url="https://example.com/3", title="Data Engineer II", description=None
    )
    session.add_all([engineer, manager, no_description])
    await session.commit()

    result = await jobs_matching_role(session, "data engineer")

    assert [job.canonical_url for job in result] == ["https://example.com/1"]


async def test_jobs_with_salary_only_returns_jobs_with_at_least_one_bound(
    session: AsyncSession,
) -> None:
    has_range = make_job(
        canonical_url="https://example.com/1", salary_min=100_000, salary_max=140_000
    )
    has_floor_only = make_job(canonical_url="https://example.com/2", salary_min=100_000)
    no_salary = make_job(canonical_url="https://example.com/3")
    session.add_all([has_range, has_floor_only, no_salary])
    await session.commit()

    result = await jobs_with_salary(session)

    assert {job.canonical_url for job in result} == {
        "https://example.com/1",
        "https://example.com/2",
    }


async def test_jobs_with_salary_filters_by_role_and_location(session: AsyncSession) -> None:
    match = make_job(
        canonical_url="https://example.com/1",
        title="Data Engineer",
        location="Remote",
        salary_min=100_000,
    )
    wrong_role = make_job(
        canonical_url="https://example.com/2",
        title="Product Manager",
        location="Remote",
        salary_min=100_000,
    )
    wrong_location = make_job(
        canonical_url="https://example.com/3",
        title="Data Engineer",
        location="Onsite",
        salary_min=100_000,
    )
    session.add_all([match, wrong_role, wrong_location])
    await session.commit()

    result = await jobs_with_salary(session, role="Data Engineer", location="Remote")

    assert [job.canonical_url for job in result] == ["https://example.com/1"]


async def test_jobs_first_seen_between_filters_range_role_and_description(
    session: AsyncSession,
) -> None:
    in_range = make_job(
        canonical_url="https://example.com/1",
        title="Data Engineer",
        description="Build pipelines.",
        first_seen=datetime(2026, 6, 5, tzinfo=UTC),
    )
    before_range = make_job(
        canonical_url="https://example.com/2",
        title="Data Engineer",
        description="Build pipelines.",
        first_seen=datetime(2026, 1, 1, tzinfo=UTC),
    )
    after_range = make_job(
        canonical_url="https://example.com/3",
        title="Data Engineer",
        description="Build pipelines.",
        first_seen=datetime(2026, 7, 1, tzinfo=UTC),
    )
    no_description = make_job(
        canonical_url="https://example.com/4",
        title="Data Engineer",
        description=None,
        first_seen=datetime(2026, 6, 6, tzinfo=UTC),
    )
    wrong_role = make_job(
        canonical_url="https://example.com/5",
        title="Product Manager",
        description="Ship things.",
        first_seen=datetime(2026, 6, 7, tzinfo=UTC),
    )
    session.add_all([in_range, before_range, after_range, no_description, wrong_role])
    await session.commit()

    result = await jobs_first_seen_between(
        session,
        datetime(2026, 6, 1, tzinfo=UTC),
        datetime(2026, 6, 30, tzinfo=UTC),
        role="Data Engineer",
    )

    assert [job.canonical_url for job in result] == ["https://example.com/1"]
