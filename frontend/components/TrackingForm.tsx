"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { updateSavedJobTracking } from "@/lib/api";

function toDatetimeLocal(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function TrackingForm({
  jobId,
  reminderAt,
  notes,
}: {
  jobId: number;
  reminderAt: string | null;
  notes: string | null;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const reminder = form.get("reminder_at") as string;
    const notesValue = form.get("notes") as string;
    setPending(true);
    try {
      await updateSavedJobTracking(jobId, {
        reminder_at: reminder ? new Date(reminder).toISOString() : null,
        notes: notesValue || null,
      });
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="text-xs text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100"
      >
        {reminderAt || notes ? "Edit reminder/notes" : "Add reminder/notes"}
      </button>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 text-sm">
      <label className="block">
        <span className="text-xs text-neutral-500">Reminder</span>
        <input
          type="datetime-local"
          name="reminder_at"
          defaultValue={toDatetimeLocal(reminderAt)}
          className="block w-full rounded-md border border-neutral-300 bg-transparent px-2 py-1 text-sm dark:border-neutral-700"
        />
      </label>
      <label className="block">
        <span className="text-xs text-neutral-500">Notes</span>
        <textarea
          name="notes"
          defaultValue={notes ?? ""}
          rows={2}
          className="block w-full rounded-md border border-neutral-300 bg-transparent px-2 py-1 text-sm dark:border-neutral-700"
        />
      </label>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={pending}
          className="rounded-md bg-neutral-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-40 dark:bg-neutral-100 dark:text-neutral-900"
        >
          {pending ? "Saving…" : "Save"}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="text-xs text-neutral-500">
          Cancel
        </button>
      </div>
    </form>
  );
}
