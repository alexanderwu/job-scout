# Job Scout — Roadmap & Tech Stack

## Guiding decisions

Settled up front so every phase below can assume them:

1. **Tool first, portfolio second.** Job Scout gets built as a tool I actually use in my own job search, then polished into a portfolio piece once the core has proven useful. The real MVP is the Phase 2 milestone — paste a resume, get ranked matches with visible reasoning — and it should be usable daily (even from a CLI) before any frontend exists. Features I personally rely on demo better than features built for demos.
2. **Source-agnostic ingestion.** hiring.cafe's internal API is the primary source, but it's unofficial: it could change, rate-limit, or block at any time. Every source sits behind a common adapter interface so that official, ToS-safe ATS board APIs (Greenhouse, Lever, Ashby — documented public endpoints per company) are cheap to add as fallbacks. This converts an existential risk into an inconvenience, and it's a better architecture story anyway.
3. **Local-first ML with swappable providers.** Embeddings and LLM generation run on free, local models by default (sentence-transformers for embeddings; a local model via Ollama for text generation). Both sit behind a thin provider interface so a paid API (Claude, OpenAI, Voyage) can be swapped in per-feature if local quality falls short — most likely candidate: cover letter drafting, where output quality is most visible.
4. **No deadline.** This is a learning project. Phases are sequenced by value, not dated; each layer gets done properly rather than rushed. If life circumstances change (e.g., an active job search with a clock), Phases 0–2 are the cut line — everything after is presentation and breadth.

## Roadmap

### Phase 0 — Setup
- Repo scaffold: `uv` for environments/dependencies, `ruff` for lint + format, `pytest`, CI (lint/test on push).
- Postgres (with pgvector) + Redis running locally via Docker Compose.
- Define the `JobSource` adapter interface (`fetch() -> list[RawPosting]`, plus pagination/rate-limit hooks) that all ingestion sources implement.
- Confirm hiring.cafe access pattern (internal API endpoints, rate limits, ToS) and build a thin client for it as the first adapter. Skim Greenhouse/Lever board API docs at the same time to sanity-check that the adapter interface fits an official source too.

### Phase 1 — Ingestion pipeline (MVP data layer)
- Scheduled worker pulls listings from all configured sources through the adapter interface and normalizes them into a single schema.
- Dedupe cross-posted jobs (same role posted via multiple ATSs) in explicit tiers, cheapest first:
  1. Exact canonical-URL / external-ID match.
  2. Normalized title + company match.
  3. (Phase 2 bonus) Embedding-similarity match for fuzzy cross-postings.
- Store raw + normalized records in Postgres. Track `first_seen`/`last_seen` for freshness and staleness detection.
- Milestone: can run ingestion on demand against ≥1 source and query "jobs added in the last 24h" from the DB. Adding a second source requires only a new adapter, no pipeline changes.

### Phase 2 — Search & matching ⭐ the real MVP
- Generate embeddings for job descriptions (batch job, local sentence-transformers model) and store in pgvector.
- Accept a resume/profile, embed it, run ANN search + filters (location, salary, seniority) to produce ranked matches.
- Add explainability: surface which skills/keywords overlapped to justify each match.
- Ship a thin CLI (`jobscout match resume.pdf`) so the tool is usable daily from this point on — no frontend required.
- Milestone: paste a resume, get ranked matches with visible reasoning. **This is the point where Job Scout becomes a tool I actually use.**

### Phase 3 — Core product (API + frontend)
*Portfolio track begins here — everything above stands on its own as a working tool.*
- FastAPI backend exposing search, match, and job-detail endpoints.
- Next.js frontend: resume upload, match list, job detail view, save/apply tracking.
- WebSocket or polling feed for "new jobs matching your profile."
- Milestone: end-to-end flow works in a browser, no manual DB queries needed.

### Phase 4 — Career copilot features
- Skill-gap analysis: diff your profile's skills against a target role's aggregate requirements across postings.
- Resume tailoring suggestions per job (highlight what to add/emphasize).
- Auto-drafted cover letters — LLM call through the provider interface (local model by default; the first candidate for swapping in a paid API if quality disappoints).
- Application tracker: saved → applied → interviewing → rejected/offer, with status timestamps and reminders.
- Milestone: a user can go from "found a job" to "tailored application submitted" inside the app.

### Phase 5 — Market insights (stretch)
- Aggregate salary/comp and in-demand-skill trends from your own ingested corpus over time.
- Simple charts: comp by role/location, skill frequency trends.
- Milestone: dashboard answers "what's this role paying right now" and "what skills are trending" from your own data.

### Phase 6 — Polish for demo
- Seed a realistic dataset (weeks of ingested history, not just a snapshot) so trends/freshness features have something to show.
- Add a lightweight ops view: ingestion throughput, query latency, cache hit rate — proof you're thinking about performance, not just CRUD.
- Cut scope ruthlessly to one smooth, fast, end-to-end story rather than many half-built features.

---

## Tech stack trade-offs

### Ingestion worker language
| Option | Pros | Cons |
|---|---|---|
| **Python (async httpx/aiohttp)** | Same language as your ML/matching code; fastest to write; huge library support | GIL limits raw CPU-bound throughput; slower per-request than compiled languages |
| Go | Excellent concurrency for high-volume polling; low memory footprint; compiles to a single binary | Second language in the stack — more context switching; smaller data/ML ecosystem |
| Node/TypeScript | Shares language with frontend; good async I/O | Weaker for any CPU-heavy normalization/dedup logic; less common for data pipelines |

Decision: Python, since ingestion here is I/O-bound (waiting on job sources, not crunching numbers), and it keeps one language across ingestion + ML. Tooling: `uv` + `ruff` + `pytest`.

### Embedding model
| Option | Pros | Cons |
|---|---|---|
| **sentence-transformers (local)** | Free, no rate limits or API keys for the bulk workload (thousands of postings); quality is fine for semantic matching at this scale; runs offline | Slower on CPU than a hosted API; model choice/tuning is on you; large first download |
| Hosted embeddings (Voyage, OpenAI) | Best-in-class quality; zero local compute; trivial code | Per-posting cost that scales with ingestion volume; API key + rate limits on the highest-volume code path; re-embedding the corpus on model changes costs real money |
| Hybrid (local bulk, API for resumes) | Cheap where volume is high, quality where it counts | Two embedding spaces don't mix — resume and job vectors must come from the same model, so this doesn't actually work for matching |

Decision: sentence-transformers locally (start with a small general model like `all-MiniLM-L6-v2`, upgrade if match quality demands it), behind an `EmbeddingProvider` interface. Note the hybrid row exists to document *why* it's rejected: query and corpus embeddings must share a model.

### LLM for explanations, tailoring, and cover letters
| Option | Pros | Cons |
|---|---|---|
| **Local model via Ollama** | Free, private (resume data never leaves the machine), no API key to manage | Noticeably weaker prose than frontier models — cover letters may need heavy editing; needs decent local hardware |
| Paid API (Claude, OpenAI) | Best output quality where it's most user-visible; low volume keeps cost trivial | API key + cost, external dependency, resume/job data leaves the machine |
| No LLM (templates + keyword diffs) | Zero cost/deps; explanations from embedding overlap alone | Generic output; can't do real tailoring or drafting |

Decision: local via Ollama by default, behind an `LLMProvider` interface with a config-switchable paid-API implementation (Claude/OpenAI). Match explanations can lean on keyword/skill overlap (cheap, deterministic) with the LLM only phrasing them; cover letters are the feature most likely to justify flipping one config value to a paid API.

### Backend API framework
| Option | Pros | Cons |
|---|---|---|
| **FastAPI (Python)** | Async native, auto-generated OpenAPI docs (nice for a demo), same language as ML code, strong typing via Pydantic | Python's raw request throughput trails Go/Node under heavy load (unlikely to matter at demo scale) |
| Node/Express or Nest | Great async I/O, single language with a Next.js frontend | Splits your ML code (Python) from your API code (JS) unless you run a separate Python service |
| Go (Gin/Fiber) | Very low latency, great concurrency | Slower to iterate; poor fit for embedding/ML calls, which usually live in Python anyway |

Decision: FastAPI. At demo scale, latency differences between these are negligible; FastAPI's docs generation and shared language with the ML pipeline outweigh raw throughput gains elsewhere.

### Database
| Option | Pros | Cons |
|---|---|---|
| **Postgres + pgvector** | One database for relational data and vector search; mature, well understood; easy to demo with plain SQL | ANN search in pgvector is slower than dedicated vector DBs at large scale (not a concern until millions of vectors) |
| Postgres + separate vector DB (Pinecone/Weaviate/Qdrant) | Purpose-built vector search, scales further | Two systems to run/sync, extra infra cost and complexity for a demo project |
| MongoDB + vector search | Flexible schema for messy scraped job data | Weaker relational guarantees for structured fields (comp, dates); less familiar to most interviewers as a "serious" backend choice |

Decision: Postgres + pgvector. One database, simpler to run and explain, and comfortably handles the data volumes a portfolio project will realistically reach.

### Caching / queueing
| Option | Pros | Cons |
|---|---|---|
| **Redis + RQ** | Battle-tested, doubles as cache and queue backend, simple mental model; RQ is minimal-config and right-sized for a single-developer project | Another moving piece to run locally/in deploy (mitigated by Docker Compose) |
| Redis + Celery | More features (complex routing, canvas workflows) | Config surface is overkill here; those features go unused |
| In-process queue (no Redis) | Zero extra infra | No persistence/retry semantics; ingestion jobs die if the process restarts; harder to demo "queue depth" as an ops metric |
| Managed queue (SQS, etc.) | Production-grade, offloads ops | Cloud lock-in and cost/complexity not worth it for a demo |

Decision: Redis + RQ (with a simple scheduler like `rq-scheduler` or APScheduler for periodic ingestion). Celery's extra machinery isn't earning its complexity at this scale, and a visible cache-hit-rate/queue-depth metric remains a good demo talking point.

### Frontend
| Option | Pros | Cons |
|---|---|---|
| **Next.js (React)** | SSR for fast first load, huge ecosystem, easy to deploy (Vercel), most employers recognize it | Slight overhead vs. plain React SPA for a small app |
| Plain React (Vite) SPA | Simpler mental model, faster local dev | No SSR — slower perceived load, worse for a "performance-focused" demo narrative |
| SvelteKit | Very fast, less boilerplate | Smaller hiring-market familiarity; more of a risk if interviewers want to dig into code they recognize |

Decision: Next.js — SSR reinforces the "we care about latency" story, and it's the most broadly recognized choice. Deferred to Phase 3; the Phase 2 CLI is the daily-driver interface until then.

### Deployment
| Option | Pros | Cons |
|---|---|---|
| **Fly.io / Render** | Cheap, simple, supports Postgres + background workers, good for demos | Less "enterprise" than AWS/GCP on a resume, though irrelevant for a working demo |
| AWS (ECS/RDS/ElastiCache) | Most resume recognition, most control | Much higher setup/ops overhead for a side project; risk of over-engineering before the product exists |
| Vercel (frontend) + Fly/Render (backend) | Best-in-class frontend deploy, simple backend | Two platforms to manage instead of one |

Decision: Vercel for the Next.js frontend, Fly.io or Render for backend + Postgres + Redis. Low ops burden, and you can narrate a clean migration path to AWS if asked in an interview. Note the local-first ML choice affects this: local embedding/LLM models need more RAM than a typical hobby-tier instance, so deployment may run embeddings on a slightly larger instance or swap the provider interface to a paid API in production while staying local for development.
