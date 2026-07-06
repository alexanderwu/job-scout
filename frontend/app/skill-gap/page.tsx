"use client";

/**
 * Skill gap: "for the role I want, what does the market ask for, and
 * what am I missing?" — aggregated from the user's own ingested
 * corpus, not generic career advice. Bars are plain CSS (share of
 * postings mentioning the skill); a chart library would be overkill
 * for horizontal bars.
 */

import { useEffect, useState } from "react";
import { api, copilot, Profile, SkillGap } from "@/lib/api";

function DemandBar({
  skill,
  share,
  count,
  kind,
}: {
  skill: string;
  share: number;
  count: number;
  kind: "have" | "missing";
}) {
  return (
    <div className="row" style={{ margin: "0.3rem 0" }}>
      <span style={{ width: "10rem" }}>
        <span className={`chip ${kind === "have" ? "match" : "gap"}`}>{skill}</span>
      </span>
      <span className="score-bar" style={{ width: "40%" }}>
        <div
          style={{
            width: `${share * 100}%`,
            background: kind === "have" ? "var(--good)" : "var(--warn)",
          }}
        />
      </span>
      <span className="muted">
        {(share * 100).toFixed(0)}% of postings ({count})
      </span>
    </div>
  );
}

export default function SkillGapPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileId, setProfileId] = useState<number | null>(null);
  const [role, setRole] = useState("");
  const [gap, setGap] = useState<SkillGap | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .listProfiles()
      .then((list) => {
        setProfiles(list);
        if (list.length > 0) setProfileId(list[0].id);
      })
      .catch((e) => setError(String(e)));
  }, []);

  async function analyze(event: React.FormEvent) {
    event.preventDefault();
    if (!profileId || !role.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setGap(await copilot.skillGap(profileId, role.trim()));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Skill gap</h1>
      <p className="muted">
        Pick a target role; Job Scout aggregates every matching posting it has
        ingested and shows which in-demand skills your resume already covers —
        and which it doesn&apos;t.
      </p>

      <form className="row" onSubmit={analyze}>
        {profiles.length > 1 && (
          <select
            value={profileId ?? undefined}
            onChange={(e) => setProfileId(Number(e.target.value))}
          >
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        )}
        <input
          type="text"
          placeholder='Target role, e.g. "data engineer"'
          value={role}
          onChange={(e) => setRole(e.target.value)}
        />
        <button type="submit" disabled={busy || !profileId}>
          {busy ? "Analyzing…" : "Analyze"}
        </button>
      </form>

      {error && <div className="error">{error}</div>}
      {profiles.length === 0 && (
        <p className="muted">Create a profile first (home page).</p>
      )}

      {gap && (
        <>
          <p className="muted">
            Based on {gap.sampled_jobs} ingested posting
            {gap.sampled_jobs === 1 ? "" : "s"} titled like “{gap.role}”.
          </p>
          {gap.sampled_jobs > 0 && (
            <>
              <div className="card">
                <h2>You already cover</h2>
                {gap.have.length === 0 && (
                  <p className="muted">None of the frequently-asked skills yet.</p>
                )}
                {gap.have.map((d) => (
                  <DemandBar key={d.skill} kind="have" {...d} />
                ))}
              </div>
              <div className="card">
                <h2>Worth adding or learning</h2>
                {gap.missing.length === 0 && (
                  <p className="muted">Nothing frequently-demanded is missing. 🎉</p>
                )}
                {gap.missing.map((d) => (
                  <DemandBar key={d.skill} kind="missing" {...d} />
                ))}
              </div>
            </>
          )}
        </>
      )}
    </>
  );
}
