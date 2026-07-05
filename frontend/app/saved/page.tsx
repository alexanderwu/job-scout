import Link from "next/link";
import { StatusControl } from "@/components/StatusControl";
import { StatusTimeline } from "@/components/StatusTimeline";
import { TrackingForm } from "@/components/TrackingForm";
import { getReminders, getSaved } from "@/lib/api";

export default async function SavedPage() {
  let saved;
  try {
    saved = await getSaved();
  } catch {
    return (
      <p className="text-sm text-red-500">
        Can&apos;t reach the Job Scout API — is <code>jobscout serve</code> running?
      </p>
    );
  }

  const reminders = await getReminders(72).catch(() => []);

  if (saved.length === 0) {
    return <p className="text-sm text-neutral-500">No saved jobs yet — save one from the matches list.</p>;
  }

  return (
    <div className="space-y-6">
      {reminders.length > 0 && (
        <section className="space-y-2 rounded-lg bg-blue-50 p-4 dark:bg-blue-950/40">
          <h2 className="text-sm font-medium">Upcoming reminders</h2>
          <ul className="space-y-1 text-sm">
            {reminders.map((entry) => (
              <li key={entry.job.id}>
                <Link href={`/jobs/${entry.job.id}`} className="hover:underline">
                  {entry.job.title}
                </Link>{" "}
                <span className="text-neutral-500">
                  — {new Date(entry.reminder_at!).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="space-y-3">
        {saved.map((entry) => (
          <div
            key={entry.job.id}
            className="space-y-3 rounded-lg border border-neutral-200 p-4 dark:border-neutral-800"
          >
            <div className="flex items-center justify-between gap-4">
              <Link href={`/jobs/${entry.job.id}`} className="min-w-0">
                <p className="truncate font-medium">{entry.job.title}</p>
                <p className="truncate text-sm text-neutral-500">
                  {entry.job.company ?? "Unknown company"}
                </p>
              </Link>
              <StatusControl jobId={entry.job.id} status={entry.status} />
            </div>
            <StatusTimeline saved={entry} />
            <TrackingForm
              jobId={entry.job.id}
              reminderAt={entry.reminder_at}
              notes={entry.notes}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
