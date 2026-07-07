# Job Scout — implementation walkthrough

A guided tour of how Job Scout is built, phase by phase, with the
reasoning behind each decision and the alternatives it beat. Read this
next to the code: every section names the modules it describes.

The commit history mirrors this document — one commit per phase, each
with a detailed message. `git log --reverse --format='%h %s'` is a
table of contents.

## The big picture

```
                     ┌─────────────────────────────────────────────┐
                     │                  sources/                   │
   Greenhouse ──────▶│  JobSource adapters (one per board API):    │
   Lever ───────────▶│  fetch() yields RawPosting                  │
   hiring.cafe ─────▶│  (+ RateLimiter politeness)                 │
                     └───────────────────┬─────────────────────────┘
                                         │ RawPosting
                     ┌───────────────────▼─────────────────────────┐
                     │            ingest/pipeline.py               │
                     │  normalize → dedupe tiers → upsert          │
                     │  postings (verbatim) + jobs (canonical)     │
                     └───────────────────┬─────────────────────────┘
                                         │ rows in Postgres (+pgvector)
                     ┌───────────────────▼─────────────────────────┐
                     │           matching/embed_jobs.py            │
                     │  EmbeddingProvider → vector per job         │
                     └───────────────────┬─────────────────────────┘
                                         │ vectors
      resume ───────▶ matching/engine.py: one SQL query =          │
                     │  cosine ANN + relational filters            │
                     │  + explain.py skill overlap                 │
                     └───────────────────┬─────────────────────────┘
                                         │ ranked, explained matches
        ┌──────────────┬─────────────────┴──────────┬──────────────┐
        │  CLI (typer) │  FastAPI (api/)            │  RQ worker   │
        │  jobscout …  │  profiles/feed/tracker/    │  rq cron →   │
        │              │  copilot/insights/ops      │  ingest+embed│
        └──────────────┘──────────┬─────────────────┴──────────────┘
                                  │ JSON
                        ┌─────────▼──────────┐
                        │ Next.js frontend   │
                        └────────────────────┘
```

Three principles from PLAN.md shaped everything:

1. **Tool first.** The CLI (`jobscout match resume.pdf`) worked before
   any web code existed; the API and UI are views over the same
   library functions, never a reimplementation.
2. **Source-agnostic ingestion.** Everything a job board is lives in
   one adapter class. The pipeline consumes `RawPosting`s and doesn't
   know Greenhouse from Lever.
3. **Local-first ML behind interfaces.** `EmbeddingProvider` and
   `LLMProvider` are the two seams where models plug in. Defaults are
   local/free; paid APIs are one `.env` change.

## Phase 1 — ingestion (`sources/`, `ingest/`, `models.py`, `normalize.py`)

**Two tables.** `postings` = what a source said, verbatim (`raw`
JSONB); `jobs` = the deduplicated opening. A cross-posted role is one
job with N postings — the dedupe decision stays inspectable, and the
UI's "Seen on" section falls out of the schema. The rejected
single-table-with-`duplicate_of_id` design makes canonicity a soft
convention every query must remember.

**Dedupe tiers, cheapest first** (`ingest/pipeline.py`):

| Tier | Key | Meaning |
|---|---|---|
| 1a | `(source, external_id)` | same posting again → refresh `last_seen` |
| 1b | canonical URL | cross-post → new posting, existing job |
| 2 | normalized title+company+location | same role, different URL |

Tier 2 skips unknown companies and splits on location. Rule of thumb
throughout: **wrong merges corrupt silently, missed merges are visible
duplicates** — so prefer precision everywhere merging is irreversible.

**Normalization** (`normalize.py`) is deliberately conservative
(casefold, punctuation, whitespace, legal suffixes) — no stemming or
synonym maps until real duplicate evidence demands them. The salary
regex is a *fallback* with sanity bounds; structured comp from a
source always wins.

**Why the `RawPosting` contract grew** (description/salary/remote):
extraction is per-source knowledge, and the adapter is the per-source
place. A central normalizer reading `raw` would need an if-ladder per
source — breaking "new source = one adapter".

**Scheduling**: RQ worker + RQ's native `rq cron` (PLAN.md predated
it; rq-scheduler/APScheduler are obsolete here). A queue instead of
crontab buys retry visibility, no overlapping runs, and an observable
queue depth (the ops page reads it).

## Phase 2 — matching (`matching/`)

**One hard rule:** query and corpus vectors must come from the same
model. Every stored vector records a `embedding_sig`
(provider+model); search filters on the current signature, so a
half-migrated corpus degrades to fewer results, never nonsense
rankings. Switching models = edit `.env`, run `jobscout embed` (the
batch job re-embeds anything with a stale signature — self-healing).

**Two providers** (`matching/embeddings.py`):
- `sentence-transformers` (all-MiniLM-L6-v2): the real default. Local,
  free, private. Lives in the optional `ml` dependency group because
  it drags in torch; `just install` includes it.
- `HashingProvider`: feature-hashed bag-of-words, L2-normalized,
  384-dim. A genuine lexical IR baseline (sklearn's HashingVectorizer
  trick), not a mock — it powers tests/CI and low-RAM machines, and
  demonstrates the provider swap actually works. Uses blake2b, not
  Python's `hash()`, because builtin hashing is salted per process.

**The ranking query** (`matching/engine.py`) is one SQL statement:
pgvector cosine distance ORDER BY plus relational WHEREs (location,
remote, salary, freshness) — filters run *in the database*, next to
the HNSW index. This is the concrete payoff of Postgres+pgvector over
a separate vector DB: no post-filter over-fetching, no two systems to
sync. The HNSW index was added by hand to the migration; autogenerate
knows nothing about vector indexes (and forgets pgvector imports —
both fixed during review, which is why migrations are reviewed code).

**Explanations** (`matching/explain.py`): deterministic set overlap
against a curated ~150-term skill vocabulary with alias folding
(golang→Go, k8s→Kubernetes). Rejected: TF-IDF top terms (junk erodes
trust), NER models (heavy dep). "Missing skills" computed here feeds
Phase 4's skill gap.

**A bug worth remembering**: match results are eager-loaded
(`selectinload`) because async SQLAlchemy *raises* on lazy loads after
the session closes (sync silently queries). Found by running the real
CLI, pinned by a regression test.

## Phase 3 — API + frontend (`api/`, `frontend/`)

- **App factory + dependency injection**: routes declare
  `SessionDep`/`ProviderDep`/`LLMDep`; tests override `get_session`
  once and drive the entire app in-process via httpx's ASGI transport.
  Nothing inside the app is mocked.
- **API schemas ≠ ORM models** (`api/schemas.py`): responses expose
  what the UI needs and hide internals (raw payloads, norm columns,
  384-float vectors); DB migrations can't accidentally become API
  breaks.
- **Profiles persist** resume text + embedding (same signature
  bookkeeping as jobs), enabling the feed and resume variants.
- **Feed = polling**, not WebSockets: ingestion runs every ~30 min, so
  push can't deliver fresher data than a 60s poll but does add
  connection state. `rank_jobs(first_seen_after=…)` is the whole feature.
- **Tracker**: `applications` + append-only `application_events` (per-
  transition timestamps answer "how long in applied?"). Status is
  TEXT+CHECK, not a PG enum — adding a stage stays a one-line
  migration. ORM gotcha fixed here: relationships to DB-cascaded
  children need `cascade="all, delete-orphan", passive_deletes=True`
  or SQLAlchemy NULLs the children's FKs on delete.
- **Frontend**: App Router; server components for reads (jobs list/
  detail, insights — real SSR), client islands for interaction. Plain
  CSS with a token block instead of Tailwind (~5 screens). `lib/api.ts`
  is the one typed client, mirroring `api/schemas.py`.

## Phase 4 — copilot (`llm.py`, `copilot/`)

One architectural rule: **a deterministic core that always works; an
LLM may only rephrase it.** Consequences: features are testable with
no model, honest by construction (the enforceable no-invention
boundary is in the deterministic layer), and `LLM_PROVIDER=none`
disables nothing — outputs are labeled scaffolds ([EDIT: …] markers in
the template cover letter make remaining human work visible).

Providers: Ollama (local/private/free) and Anthropic (quality escape
hatch, plain httpx — one POST doesn't justify an SDK). Both tested via
mock transports: request shape, auth headers, and failure messages are
pinned; only the services themselves are untested here.

Skill gap samples by **title substring, not embedding similarity**, so
the denominator is auditable ("these 43 postings titled data
engineer"). Reminders are **derived at read time** (idle, non-terminal
applications), not cron-written rows that could drift.

## Phase 5 — insights (`insights.py`)

- Salary p25/median/p75 via Postgres `percentile_cont` — the database
  has an ordered-set aggregate for exactly this; percentiles because
  salary data is skewed and gappy.
- Skill trends: Python-side extraction (the curated vocabulary) over a
  bounded recent window, emitted as dense zero-filled weekly series so
  sparklines align. Upgrade path if the corpus grows: materialize
  skills at ingest time.
- Charts are ~30 lines of inline SVG (`components/Sparkline.tsx`).
- Every view shows its sample size: this is your corpus, not a market
  survey.

## Phase 6 — polish (`seed.py`, `api/routes/ops.py`)

- **Seeder** (`jobscout seed`): fabricates weeks of history *through
  the real pipeline* (backdated `fetched_at`), so seeded rows exercised
  the same dedupe/salary/backfill code as live data. Deterministic RNG;
  everything tagged `seed_*`; `--wipe` removes exactly its own rows.
- **Ops** (`/ops` + `/ops` page): all gauges derived from systems
  already running — pg_stat_database cache hit ratio, Redis INFO +
  RQ queue depth, a timed real vector search for match latency, corpus/
  freshness counts. Degrades gracefully (Redis down → nulls, not 500).

## Working on the codebase

| Task | Where to start |
|---|---|
| Add a job source | subclass `JobSource` in `sources/`, register in `ingest/registry.py`, add fixture tests |
| Add a skill to explanations | one line in `matching/explain.py` `_CANON` |
| Switch embedding model | `.env` `EMBEDDING_MODEL`, then `jobscout embed` (dimension change = migration) |
| Enable LLM prose | `.env` `LLM_PROVIDER=ollama` (or `anthropic` + key) |
| Change the schema | edit `models.py`, `just makemigration "…"`, **review the draft**, `just migrate` |
| New API endpoint | route module in `api/routes/`, schemas in `api/schemas.py`, test in `tests/test_api.py` |

### Verification habits this repo relies on

- `just check` = format + lint + strict mypy + pytest; CI runs the same
  plus a frontend typecheck/build. DB-dependent tests run against real
  Postgres (migrated by Alembic — every test run re-proves the
  migration chain) and skip with instructions when no DB is available.
- External HTTP is tested with `httpx.MockTransport` fixtures that pin
  request/response contracts (adapters, LLM providers).
- Two things intentionally still need a human with network access:
  hiring.cafe's live API shape (`sources/hiring_cafe.py` warning), and
  live Greenhouse/Lever pulls (`GREENHOUSE_BOARDS=<some-board>` then
  `jobscout ingest` — the fixtures mirror documented shapes, so
  surprises should be small).
