"use client";

import { useState } from "react";
import { ApiError, generateCoverLetter, type CoverLetter } from "@/lib/api";

export function CoverLetterPanel({
  jobId,
  initialCoverLetter,
}: {
  jobId: number;
  initialCoverLetter: CoverLetter | null;
}) {
  const [coverLetter, setCoverLetter] = useState(initialCoverLetter);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    setPending(true);
    setError(null);
    try {
      setCoverLetter(await generateCoverLetter(jobId));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setError("Upload a resume first — cover letters are tailored to your profile.");
      } else if (err instanceof ApiError && err.status === 502) {
        setError("Generation failed — is Ollama running?");
      } else {
        setError("Generation failed — try again.");
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-medium">Cover Letter</h2>
        <button
          onClick={handleGenerate}
          disabled={pending}
          className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium disabled:opacity-40 dark:border-neutral-700"
        >
          {pending ? "Drafting…" : coverLetter ? "Regenerate" : "Generate"}
        </button>
      </div>
      {pending && (
        <p className="text-sm text-neutral-500">
          Drafting with the local model — this can take a minute.
        </p>
      )}
      {error && <p className="text-sm text-red-500">{error}</p>}
      {coverLetter && (
        <textarea
          readOnly
          value={coverLetter.content}
          rows={12}
          className="w-full rounded-md border border-neutral-200 bg-transparent p-3 text-sm leading-relaxed dark:border-neutral-800"
        />
      )}
    </section>
  );
}
