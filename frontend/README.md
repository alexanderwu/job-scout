# Job Scout — web frontend (Phase 3)

Next.js (App Router, TypeScript) UI over the FastAPI backend.

```sh
npm install
npm run dev        # http://localhost:3000 — needs the API running (just api)
```

Set `NEXT_PUBLIC_API_URL` if the API isn't at `http://localhost:8000`.

## Layout

| Path | What it is |
|---|---|
| `app/page.tsx` | Create/pick a profile (resume upload or paste) |
| `app/matches/[profileId]/` | Ranked matches + filters + 60s "new jobs" poll |
| `app/jobs/` | Browse recent jobs (server-rendered) |
| `app/jobs/[id]/` | Job detail: every posting/source, description |
| `app/tracker/` | Application pipeline (saved → … → offer) |
| `lib/api.ts` | The typed API client — mirrors `api/schemas.py` |
| `components/` | Client-side islands (match card, save button) |

## Design notes

- **Server components for reads, client components for interaction.**
  Job browsing/detail render on the server (fast first paint, real SSR);
  forms, filters, and the tracker are client islands.
- **Polling, not WebSockets**, for "new jobs matching your profile":
  ingestion runs every ~30 min, so a 60s poll is as fresh as push with
  none of the connection management.
- **Plain CSS, no framework**: ~5 screens; the token block at the top of
  `app/globals.css` is the entire design system.
