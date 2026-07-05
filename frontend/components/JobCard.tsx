import Link from "next/link";
import type { JobSummary } from "@/lib/api";

export function JobCard({
  job,
  score,
  matchedKeywords,
}: {
  job: JobSummary;
  score?: number | null;
  matchedKeywords?: string[];
}) {
  return (
    <Link
      href={`/jobs/${job.id}`}
      className="block rounded-lg border border-neutral-200 p-4 transition-colors hover:border-neutral-400 dark:border-neutral-800 dark:hover:border-neutral-600"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="truncate font-medium">{job.title}</h3>
          <p className="truncate text-sm text-neutral-500">
            {job.company ?? "Unknown company"} — {job.location ?? "Location unspecified"}
          </p>
        </div>
        {score != null && (
          <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
            {Math.round(score * 100)}% match
          </span>
        )}
      </div>
      {matchedKeywords && matchedKeywords.length > 0 && (
        <p className="mt-2 text-xs text-neutral-500">matched: {matchedKeywords.join(", ")}</p>
      )}
    </Link>
  );
}
