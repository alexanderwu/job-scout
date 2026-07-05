import { notFound } from "next/navigation";
import { CoverLetterPanel } from "@/components/CoverLetterPanel";
import { StatusControl } from "@/components/StatusControl";
import { ApiError, getCoverLetter, getJob, getTailoring } from "@/lib/api";

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

  const tailoring = await getTailoring(jobId).catch(() => null);
  const coverLetter = await getCoverLetter(jobId).catch(() => null);

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

      {tailoring && (tailoring.matched_keywords.length > 0 || tailoring.missing_keywords.length > 0) && (
        <section className="space-y-2">
          <h2 className="font-medium">Tailoring Suggestions</h2>
          {tailoring.missing_keywords.length > 0 && (
            <p className="text-sm text-neutral-500">
              Consider adding: {tailoring.missing_keywords.join(", ")}
            </p>
          )}
          {tailoring.matched_keywords.length > 0 && (
            <p className="text-sm text-neutral-500">
              Already emphasized: {tailoring.matched_keywords.join(", ")}
            </p>
          )}
        </section>
      )}

      <CoverLetterPanel jobId={job.id} initialCoverLetter={coverLetter} />
    </article>
  );
}
