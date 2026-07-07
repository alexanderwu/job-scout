/**
 * Ops view (Phase 6): the system's own health, one glance. Server
 * component — it's a read of GET /ops, re-fetched per page load.
 */

import { API_URL } from "@/lib/api";

export const dynamic = "force-dynamic";

interface OpsReport {
  corpus: {
    jobs: number;
    postings: number;
    embedded: number;
    embedding_coverage: number;
    new_last_24h: number;
    active: number;
    stale: number;
  };
  newest_job_seen: string | null;
  last_ingest_activity: string | null;
  match_latency_ms: number;
  pg_cache_hit_ratio: number | null;
  queue: {
    reachable: boolean;
    queue_depth: number | null;
    failed_jobs: number | null;
    keyspace_hit_ratio: number | null;
  };
}

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="card" style={{ minWidth: "11rem", flex: "1 1 11rem" }}>
      <div className="muted">{label}</div>
      <strong style={{ fontSize: "1.5rem" }}>{value}</strong>
      {hint && <div className="muted">{hint}</div>}
    </div>
  );
}

const pct = (v: number | null) => (v === null ? "n/a" : `${(v * 100).toFixed(1)}%`);

export default async function OpsPage() {
  const report: OpsReport = await (
    await fetch(`${API_URL}/ops`, { cache: "no-store" })
  ).json();
  const { corpus, queue } = report;

  return (
    <>
      <h1>Ops</h1>

      <h2>Corpus</h2>
      <div className="row">
        <Tile label="jobs" value={String(corpus.jobs)} hint={`${corpus.postings} postings`} />
        <Tile
          label="embedded"
          value={pct(corpus.embedding_coverage)}
          hint={`${corpus.embedded} vectors`}
        />
        <Tile label="new (24h)" value={String(corpus.new_last_24h)} />
        <Tile
          label="active / stale"
          value={`${corpus.active} / ${corpus.stale}`}
          hint="stale = not seen in 45d"
        />
      </div>

      <h2>Performance</h2>
      <div className="row">
        <Tile
          label="match query latency"
          value={`${report.match_latency_ms.toFixed(0)} ms`}
          hint="embed probe + ANN search, end to end"
        />
        <Tile
          label="Postgres cache hit"
          value={pct(report.pg_cache_hit_ratio)}
          hint="shared_buffers vs disk reads"
        />
        <Tile
          label="Redis cache hit"
          value={queue.reachable ? pct(queue.keyspace_hit_ratio) : "redis down"}
        />
      </div>

      <h2>Ingestion</h2>
      <div className="row">
        <Tile
          label="queue depth"
          value={queue.reachable ? String(queue.queue_depth ?? 0) : "redis down"}
          hint={
            queue.reachable && queue.failed_jobs
              ? `${queue.failed_jobs} failed job(s)!`
              : "ingest queue"
          }
        />
        <Tile
          label="last ingest activity"
          value={
            report.last_ingest_activity
              ? new Date(report.last_ingest_activity).toLocaleString()
              : "never"
          }
        />
        <Tile
          label="newest job"
          value={
            report.newest_job_seen
              ? new Date(report.newest_job_seen).toLocaleString()
              : "never"
          }
        />
      </div>
    </>
  );
}
