"use client";

/**
 * One ranked match: score bar, salary, skill chips (green = shared,
 * amber = the job wants it and the resume lacks it), save button.
 * The explanation chips ARE the product's differentiator — they get
 * visual priority over everything except the title.
 */

import Link from "next/link";
import { useState } from "react";
import { api, formatSalary, Match } from "@/lib/api";

export default function MatchCard({
  match,
  profileId,
}: {
  match: Match;
  profileId?: number;
}) {
  const [saved, setSaved] = useState(false);
  const { job, explanation } = match;

  async function save() {
    try {
      await api.saveJob(job.id, profileId);
      setSaved(true);
    } catch (e) {
      alert(String(e));
    }
  }

  return (
    <div className="card">
      <div className="row spread">
        <span className="score" title="cosine similarity to your profile">
          <span className="score-bar">
            <div style={{ width: `${Math.max(0, match.score) * 100}%` }} />
          </span>
          <strong>{(match.score * 100).toFixed(0)}%</strong>
        </span>
        <button className="secondary" onClick={save} disabled={saved}>
          {saved ? "Saved ✓" : "Save"}
        </button>
      </div>
      <h2 style={{ margin: "0.25rem 0" }}>
        <Link href={`/jobs/${job.id}`}>{job.title}</Link>
      </h2>
      <div className="muted">
        {job.company ?? "Unknown company"} · {job.location ?? "location n/a"}
        {job.remote && !/remote/i.test(job.location ?? "") ? " · remote" : ""}
        {formatSalary(job) ? ` · ${formatSalary(job)}` : ""}
      </div>
      <div className="chips">
        {explanation.overlapping.map((s) => (
          <span key={s} className="chip match" title="you both mention this">
            {s}
          </span>
        ))}
        {explanation.missing.map((s) => (
          <span key={s} className="chip gap" title="the job wants this; your resume doesn't mention it">
            {s} ?
          </span>
        ))}
      </div>
      {match.apply_url && (
        <a href={match.apply_url} target="_blank" rel="noreferrer">
          Apply ↗
        </a>
      )}
    </div>
  );
}
