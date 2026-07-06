"use client";

/**
 * The main screen: ranked matches for a profile, with filters and a
 * polling "new jobs" banner.
 *
 * Polling (60s) instead of a WebSocket: ingestion runs every ~30
 * minutes, so push infra would deliver news no faster than a poll
 * while adding connection state to manage. The banner appears when
 * the feed has jobs the list hasn't shown yet; clicking refreshes.
 */

import { use, useCallback, useEffect, useRef, useState } from "react";
import MatchCard from "@/components/MatchCard";
import { api, MatchResponse } from "@/lib/api";

const FEED_POLL_MS = 60_000;
const FEED_WINDOW_HOURS = 24;

export default function MatchesPage({
  params,
}: {
  params: Promise<{ profileId: string }>;
}) {
  const { profileId } = use(params);
  const [data, setData] = useState<MatchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [location, setLocation] = useState("");
  const [remoteOnly, setRemoteOnly] = useState(false);
  const [minSalary, setMinSalary] = useState("");
  const [newCount, setNewCount] = useState(0);
  const loadedAt = useRef<Date>(new Date());

  const load = useCallback(async () => {
    setError(null);
    try {
      const result = await api.matchProfile(profileId, {
        location: location || undefined,
        remote_only: remoteOnly,
        min_salary: minSalary ? Number(minSalary) : undefined,
      });
      setData(result);
      loadedAt.current = new Date();
      setNewCount(0);
    } catch (e) {
      setError(String(e));
    }
  }, [profileId, location, remoteOnly, minSalary]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const timer = setInterval(async () => {
      try {
        const feed = await api.feed(profileId, FEED_WINDOW_HOURS);
        const fresh = feed.matches.filter(
          (m) => new Date(m.job.first_seen) > loadedAt.current,
        );
        setNewCount(fresh.length);
      } catch {
        // polling is best-effort; next tick retries
      }
    }, FEED_POLL_MS);
    return () => clearInterval(timer);
  }, [profileId]);

  return (
    <>
      <h1>Your matches</h1>

      {newCount > 0 && (
        <div className="banner row spread">
          <span>
            {newCount} new job{newCount > 1 ? "s" : ""} matching your profile
            since you loaded this page.
          </span>
          <button onClick={load}>Show</button>
        </div>
      )}

      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          load();
        }}
      >
        <input
          type="text"
          placeholder="Location contains…"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
        />
        <input
          type="number"
          placeholder="Min salary"
          value={minSalary}
          onChange={(e) => setMinSalary(e.target.value)}
        />
        <label className="row" style={{ gap: "0.3rem" }}>
          <input
            type="checkbox"
            checked={remoteOnly}
            onChange={(e) => setRemoteOnly(e.target.checked)}
          />
          remote only
        </label>
        <button type="submit">Filter</button>
      </form>

      {data?.resume_skills.length ? (
        <p className="muted">
          Skills read from your resume:{" "}
          <span className="chips" style={{ display: "inline-flex" }}>
            {data.resume_skills.map((s) => (
              <span key={s} className="chip">
                {s}
              </span>
            ))}
          </span>
        </p>
      ) : null}

      {error && <div className="error">{error}</div>}
      {!data && !error && <p className="muted">Loading matches…</p>}
      {data?.matches.length === 0 && (
        <p className="muted">
          No matches — has ingestion run? (<code>jobscout ingest</code>)
        </p>
      )}
      {data?.matches.map((m) => (
        <MatchCard key={m.job.id} match={m} profileId={Number(profileId)} />
      ))}
    </>
  );
}
