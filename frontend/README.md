# Frontend (Phase 3)

The Next.js web app described in `PLAN.md` Phase 3: resume upload, ranked
match list, job detail, and a saved/applied tracker, talking to the
FastAPI backend in `backend/`.

See the repo root `README.md`'s "Running the frontend" section for setup.
Quick version:

```sh
npm install
cp .env.local.example .env.local   # points at the API; defaults to localhost:8000
npm run dev                        # http://localhost:3000
```

The backend (`jobscout serve`, or `just serve` from the repo root) needs
to be running for any page to load data.

## Layout

```
app/                  Next.js App Router pages (/, /jobs/[id], /saved).
components/           Shared UI: NavBar, JobCard, ResumeUpload, StatusControl, FeedBanner.
lib/api.ts            Typed client for the backend API (mirrors backend/src/jobscout/api/schemas.py).
```
