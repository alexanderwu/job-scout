"use client";

/**
 * The copilot island on a job's detail page: tailoring advice and a
 * cover-letter draft, computed against one of your profiles.
 *
 * When the backend runs without an LLM (the default), results are the
 * deterministic versions — suggestions as bullets, the letter as an
 * [EDIT]-marked scaffold — and the UI labels them accordingly, so
 * nobody mistakes a template for finished prose.
 */

import { useEffect, useState } from "react";
import {
  api,
  copilot,
  CoverLetter,
  Profile,
  TailorAdvice,
} from "@/lib/api";

export default function CopilotPanel({ jobId }: { jobId: number }) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileId, setProfileId] = useState<number | null>(null);
  const [advice, setAdvice] = useState<TailorAdvice | null>(null);
  const [letter, setLetter] = useState<CoverLetter | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listProfiles()
      .then((list) => {
        setProfiles(list);
        if (list.length > 0) setProfileId(list[0].id);
      })
      .catch((e) => setError(String(e)));
  }, []);

  if (profiles.length === 0) {
    return (
      <p className="muted">
        Create a profile on the home page to unlock tailoring advice and
        cover-letter drafts for this job.
      </p>
    );
  }

  async function run(kind: "tailor" | "letter") {
    if (!profileId) return;
    setBusy(kind);
    setError(null);
    try {
      if (kind === "tailor") setAdvice(await copilot.tailor(jobId, profileId));
      else setLetter(await copilot.coverLetter(jobId, profileId));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="card">
      <div className="row">
        <strong>Copilot</strong>
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
        <button onClick={() => run("tailor")} disabled={busy !== null}>
          {busy === "tailor" ? "Thinking…" : "Tailoring advice"}
        </button>
        <button onClick={() => run("letter")} disabled={busy !== null}>
          {busy === "letter" ? "Drafting…" : "Draft cover letter"}
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {advice && (
        <>
          <h2>How to tailor your resume</h2>
          <ul>
            {advice.suggestions.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
          {advice.prose && <p>{advice.prose}</p>}
        </>
      )}

      {letter && (
        <>
          <h2>
            Cover letter{" "}
            <span className="muted">
              ({letter.generated_by === "template"
                ? "template — fill in the [EDIT] parts"
                : `drafted by ${letter.generated_by} — verify every claim`})
            </span>
          </h2>
          <pre className="description">{letter.body}</pre>
        </>
      )}
    </div>
  );
}
