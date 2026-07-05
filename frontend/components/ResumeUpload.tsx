"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { uploadResume } from "@/lib/api";

export function ResumeUpload({ compact }: { compact?: boolean }) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await uploadResume(file);
      setFile(null);
      router.refresh();
    } catch {
      setError("Upload failed — check that the file is a .pdf, .txt, or .md.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-wrap items-center gap-3">
      <input
        type="file"
        accept=".pdf,.txt,.md"
        onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        className="text-sm"
      />
      <button
        type="submit"
        disabled={!file || uploading}
        className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40 dark:bg-neutral-100 dark:text-neutral-900"
      >
        {uploading ? "Uploading…" : compact ? "Replace resume" : "Upload resume"}
      </button>
      {error && <p className="w-full text-sm text-red-500">{error}</p>}
    </form>
  );
}
