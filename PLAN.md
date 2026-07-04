# Job Scout — Roadmap & Tech Stack

## Roadmap

### Phase 0 — Setup (few days)
- Repo scaffold, CI (lint/test on push), Postgres + Redis running locally via Docker Compose.
- Confirm hiring.cafe access pattern (internal API endpoints, rate limits, ToS) and build a thin client for it.

### Phase 1 — Ingestion pipeline (MVP data layer)
- Scheduled worker pulls listings from hiring.cafe, normalizes into a single schema, dedupes cross-posted jobs (same role posted via multiple ATSs).
- Store raw + normalized records in Postgres. Track `first_seen`/`last_seen` for freshness and staleness detection.
- Milestone: can run ingestion on demand and query "jobs added in the last 24h" from the DB.

### Phase 2 — Search & matching
- Generate embeddings for job descriptions (batch job) and store in pgvector.
- Accept a resume/profile, embed it, run ANN search + filters (location, salary, seniority) to produce ranked matches.
- Add explainability: surface which skills/keywords overlapped to justify each match.
- Milestone: paste a resume, get ranked matches with visible reasoning.

### Phase 3 — Core product (API + frontend)
- FastAPI backend exposing search, match, and job-detail endpoints.
- Next.js frontend: resume upload, match list, job detail view, save/apply tracking.
- WebSocket or polling feed for "new jobs matching your profile."
- Milestone: end-to-end flow works in a browser, no manual DB queries needed.

### Phase 4 — Career copilot features
- Skill-gap analysis: diff your profile's skills against a target role's aggregate requirements across postings.
- Resume tailoring suggestions per job (highlight what to add/emphasize).
- Auto-drafted cover letters (LLM call, templated).
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

Recommendation: Python, since ingestion here is I/O-bound (waiting on hiring.cafe, not crunching numbers), and it keeps one language across ingestion + ML.

### Backend API framework
| Option | Pros | Cons |
|---|---|---|
| **FastAPI (Python)** | Async native, auto-generated OpenAPI docs (nice for a demo), same language as ML code, strong typing via Pydantic | Python's raw request throughput trails Go/Node under heavy load (unlikely to matter at demo scale) |
| Node/Express or Nest | Great async I/O, single language with a Next.js frontend | Splits your ML code (Python) from your API code (JS) unless you run a separate Python service |
| Go (Gin/Fiber) | Very low latency, great concurrency | Slower to iterate; poor fit for embedding/ML calls, which usually live in Python anyway |

Recommendation: FastAPI. At demo scale, latency differences between these are negligible; FastAPI's docs generation and shared language with the ML pipeline outweigh raw throughput gains elsewhere.

### Database
| Option | Pros | Cons |
|---|---|---|
| **Postgres + pgvector** | One database for relational data and vector search; mature, well understood; easy to demo with plain SQL | ANN search in pgvector is slower than dedicated vector DBs at large scale (not a concern until millions of vectors) |
| Postgres + separate vector DB (Pinecone/Weaviate/Qdrant) | Purpose-built vector search, scales further | Two systems to run/sync, extra infra cost and complexity for a demo project |
| MongoDB + vector search | Flexible schema for messy scraped job data | Weaker relational guarantees for structured fields (comp, dates); less familiar to most interviewers as a "serious" backend choice |

Recommendation: Postgres + pgvector. One database, simpler to run and explain, and comfortably handles the data volumes a portfolio project will realistically reach.

### Caching / queueing
| Option | Pros | Cons |
|---|---|---|
| **Redis (cache + Celery/RQ queue)** | Battle-tested, doubles as cache and queue backend, simple mental model | Another moving piece to run locally/in deploy (mitigated by Docker Compose) |
| In-process queue (no Redis) | Zero extra infra | No persistence/retry semantics; ingestion jobs die if the process restarts; harder to demo "queue depth" as an ops metric |
| Managed queue (SQS, etc.) | Production-grade, offloads ops | Cloud lock-in and cost/complexity not worth it for a demo |

Recommendation: Redis. It's cheap to run, and having a visible cache-hit-rate/queue-depth metric is a good demo talking point.

### Frontend
| Option | Pros | Cons |
|---|---|---|
| **Next.js (React)** | SSR for fast first load, huge ecosystem, easy to deploy (Vercel), most employers recognize it | Slight overhead vs. plain React SPA for a small app |
| Plain React (Vite) SPA | Simpler mental model, faster local dev | No SSR — slower perceived load, worse for a "performance-focused" demo narrative |
| SvelteKit | Very fast, less boilerplate | Smaller hiring-market familiarity; more of a risk if interviewers want to dig into code they recognize |

Recommendation: Next.js — SSR reinforces the "we care about latency" story, and it's the most broadly recognized choice.

### Deployment
| Option | Pros | Cons |
|---|---|---|
| **Fly.io / Render** | Cheap, simple, supports Postgres + background workers, good for demos | Less "enterprise" than AWS/GCP on a resume, though irrelevant for a working demo |
| AWS (ECS/RDS/ElastiCache) | Most resume recognition, most control | Much higher setup/ops overhead for a side project; risk of over-engineering before the product exists |
| Vercel (frontend) + Fly/Render (backend) | Best-in-class frontend deploy, simple backend | Two platforms to manage instead of one |

Recommendation: Vercel for the Next.js frontend, Fly.io or Render for backend + Postgres + Redis. Low ops burden, and you can narrate a clean migration path to AWS if asked in an interview.
