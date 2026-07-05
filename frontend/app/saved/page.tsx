import Link from "next/link";
import { StatusControl } from "@/components/StatusControl";
import { getSaved } from "@/lib/api";

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

  if (saved.length === 0) {
    return <p className="text-sm text-neutral-500">No saved jobs yet — save one from the matches list.</p>;
  }

  return (
    <div className="space-y-3">
      {saved.map((entry) => (
        <div
          key={entry.job.id}
          className="flex items-center justify-between gap-4 rounded-lg border border-neutral-200 p-4 dark:border-neutral-800"
        >
          <Link href={`/jobs/${entry.job.id}`} className="min-w-0">
            <p className="truncate font-medium">{entry.job.title}</p>
            <p className="truncate text-sm text-neutral-500">
              {entry.job.company ?? "Unknown company"}
            </p>
          </Link>
          <StatusControl jobId={entry.job.id} status={entry.status} />
        </div>
      ))}
    </div>
  );
}
