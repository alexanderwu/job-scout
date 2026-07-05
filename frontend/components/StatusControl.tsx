"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { SAVED_STATUSES, type SavedStatus, saveJob, unsaveJob, updateSavedStatus } from "@/lib/api";

export function StatusControl({ jobId, status }: { jobId: number; status: SavedStatus | null }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);

  async function handleChange(next: SavedStatus) {
    setPending(true);
    try {
      if (status === null) {
        await saveJob(jobId, next);
      } else {
        await updateSavedStatus(jobId, next);
      }
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  async function handleUnsave() {
    setPending(true);
    try {
      await unsaveJob(jobId);
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  if (status === null) {
    return (
      <button
        disabled={pending}
        onClick={() => handleChange("saved")}
        className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium disabled:opacity-40 dark:border-neutral-700"
      >
        {pending ? "Saving…" : "Save job"}
      </button>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <select
        value={status}
        disabled={pending}
        onChange={(event) => handleChange(event.target.value as SavedStatus)}
        className="rounded-md border border-neutral-300 bg-transparent px-2 py-1.5 text-sm disabled:opacity-40 dark:border-neutral-700"
      >
        {SAVED_STATUSES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
      <button
        disabled={pending}
        onClick={handleUnsave}
        className="text-sm text-neutral-500 hover:text-red-500 disabled:opacity-40"
      >
        remove
      </button>
    </div>
  );
}
