import { notFound } from "next/navigation";
import { StatusControl } from "@/components/StatusControl";
import { ApiError, getJob } from "@/lib/api";

export default async function JobDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const jobId = Number(id);

  let job;
  try {
    job = await getJob(jobId);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      notFound();
    }
    return (
      <p className="text-sm text-red-500">
        Can&apos;t reach the Job Scout API — is <code>jobscout serve</code> running?
      </p>
    );
  }

  return (
    <article className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">{job.title}</h1>
        <p className="text-neutral-500">
          {job.company ?? "Unknown company"} — {job.location ?? "Location unspecified"}
        </p>
      </div>

      <StatusControl jobId={job.id} status={job.saved_status} />

      {job.canonical_url && (
        <a
          href={job.canonical_url}
          target="_blank"
          rel="noreferrer"
          className="block text-sm text-blue-600 hover:underline dark:text-blue-400"
        >
          View original posting ↗
        </a>
      )}

      <div className="whitespace-pre-wrap text-sm leading-relaxed">
        {job.description ?? "No description available."}
      </div>
    </article>
  );
}
