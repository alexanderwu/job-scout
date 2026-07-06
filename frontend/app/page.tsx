"use client";

/**
 * Home: create a profile (upload or paste a resume) and pick an
 * existing one. A client component — it's all form state and
 * mutations; there's nothing here SSR could render meaningfully
 * before the user acts.
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, Profile } from "@/lib/api";

export default function HomePage() {
  const router = useRouter();
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listProfiles().then(setProfiles).catch((e) => setError(String(e)));
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.set("name", name || "default");
      if (file) form.set("file", file);
      else if (text.trim()) form.set("text", text);
      else throw new Error("Upload a resume file or paste its text first.");
      const profile = await api.createProfile(form);
      router.push(`/matches/${profile.id}`);
    } catch (e) {
      setError(String(e));
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Find jobs that actually fit</h1>
      <p className="muted">
        Job Scout compares the <em>meaning</em> of your resume against every
        ingested posting and explains each match. Your resume is processed
        locally by the backend — it never leaves your machine.
      </p>

      {profiles.length > 0 && (
        <>
          <h2>Your profiles</h2>
          {profiles.map((p) => (
            <div key={p.id} className="card row spread">
              <div>
                <a href={`/matches/${p.id}`}>
                  <strong>{p.name}</strong>
                </a>
                <div className="chips">
                  {p.skills.slice(0, 10).map((s) => (
                    <span key={s} className="chip">
                      {s}
                    </span>
                  ))}
                </div>
              </div>
              <button onClick={() => router.push(`/matches/${p.id}`)}>
                View matches
              </button>
            </div>
          ))}
        </>
      )}

      <h2>New profile</h2>
      <form className="card" onSubmit={submit}>
        <div className="row">
          <label htmlFor="name">Name</label>
          <input
            id="name"
            type="text"
            placeholder="e.g. data-engineering"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <p className="muted">
          Upload a resume (.pdf, .txt, .md) — or paste the text below.
        </p>
        <input
          type="file"
          accept=".pdf,.txt,.md"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <p className="muted">…or paste:</p>
        <textarea
          placeholder="Paste your resume text here"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        {error && <div className="error">{error}</div>}
        <p>
          <button type="submit" disabled={busy}>
            {busy ? "Matching…" : "Create profile & match"}
          </button>
        </p>
      </form>
    </>
  );
}
