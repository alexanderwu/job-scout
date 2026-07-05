# Job Scout

Job Scout is a personal job-search assistant that goes beyond keyword search. Instead of scrolling through hundreds of listings, you get a ranked list of jobs matched to your actual skills and experience, with a plain-English explanation of *why* each one is a good fit — plus tools to close the gap between where you are and where you want to be.

I built this while running my own job search, because every existing job board answers "what's out there" but not "what's actually right for me, and what am I missing."

## Why this project exists

Job boards are search engines: you type keywords, you get thousands of results, and you're on your own to figure out which ones matter. Job Scout is designed to work more like a research assistant: it reads job postings the way a person would, compares them against your background, and tells you where you stand.

The goal isn't just a bigger list of jobs. It's a smaller, smarter one — with the context to act on it.

## What it does

**Finds relevant jobs, automatically.** Job Scout continuously pulls in fresh job postings and keeps them organized and de-duplicated, so you're always looking at current openings instead of stale or repeated listings.

**Matches jobs to you, not just to a search box.** Rather than relying on exact keyword matches, Job Scout compares the meaning of a job posting to your background and experience, so it can surface strong-fit roles even when the wording is different from your resume.

**Explains its reasoning.** Every match comes with a plain-language explanation of which skills and experience lined up, so you can trust the recommendation instead of wondering why a job showed up.

**Helps you close the gap.** For any role you're interested in, Job Scout can show you what skills or experience tend to separate a strong candidate from a typical applicant, and suggest how to tailor your resume and cover letter for that specific job.

**Tracks your applications.** A simple pipeline view (saved, applied, interviewing, offer) keeps your job search organized in one place instead of a spreadsheet.

**Shows you the market.** Aggregated salary and in-demand-skill trends give a real-time sense of what roles are actually paying and what employers are asking for right now.

## The vision

Long-term, Job Scout is meant to be a career co-pilot, not just a job board: a single place to discover roles, understand where you're competitive, prepare tailored applications, and track the whole process — all grounded in real, current market data rather than generic advice.

## How it's built

A few principles guide every technical decision (the full reasoning is in `PLAN.md`):

- **Tool first, portfolio second.** Job Scout is built to be used daily in a real job search — the matching core ships with a CLI long before there's a web frontend, and only features that prove useful get polished for show.
- **Source-agnostic ingestion.** Job postings come in through a common adapter interface, so no single job board or API is a point of failure — new sources are a new adapter, not a pipeline rewrite.
- **Local-first ML, swappable providers.** Embeddings and text generation run on free local models by default (your resume never has to leave your machine), with a provider interface that lets a paid API be swapped in per-feature where output quality matters most.

## Current status

Job Scout is at the foundations stage: the roadmap and tech stack are settled (see `PLAN.md`), and implementation is starting with the ingestion pipeline. The features described above are the target design — this README describes where the project is headed, and the status here will track what's actually built.

- **Done (Phase 0):** project scaffold (`uv`/`ruff`/`mypy`/`pytest`, CI), local Postgres+pgvector and Redis via Docker Compose, the `JobSource` adapter interface, and a first hiring.cafe adapter (tested against fixtures; live API shape still needs manual confirmation).
- **Next up:** the ingestion pipeline that collects, normalizes, and de-duplicates job postings (Phase 1).
- **Then:** the matching engine that ranks jobs against a candidate profile, with a CLI to use it daily (Phase 2 — the real MVP).
- **Later:** web frontend, career-copilot features (skill-gap analysis, resume tailoring, cover letters), application tracker, and market-insight dashboards.

## Development

Requires [uv](https://docs.astral.sh/uv/) (manages Python and dependencies) and Docker.

```sh
uv sync                    # create .venv with the pinned Python + all deps
docker compose up -d       # local Postgres (with pgvector) + Redis
cp .env.example .env       # local connection strings

uv run pytest              # tests
uv run ruff format .       # format
uv run ruff check .        # lint
uv run mypy                # type check (strict)
```

CI runs the same four checks on every push and pull request (`.github/workflows/ci.yml`).

## About this project

This project reflects how I approach engineering problems: start from a real need (my own job search), build something that actually works end to end, and make deliberate, defensible choices along the way rather than defaulting to whatever's trendy. It's also a sandbox for the parts of data and ML engineering I care most about — building pipelines that keep data fresh, and turning unstructured text into something a system can reason about and explain.
