/**
 * Job detail — server component (SSR). Shows every posting we've seen
 * for this job: the visible payoff of the postings/jobs split (a
 * cross-posted role lists each source with its own URL and dates).
 */

import { api, formatSalary } from "@/lib/api";
import CopilotPanel from "@/components/CopilotPanel";
import SaveButton from "@/components/SaveButton";

export const dynamic = "force-dynamic";

export default async function JobPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const job = await api.getJob(id);

  return (
    <>
      <h1>{job.title}</h1>
      <p className="muted">
        {job.company ?? "?"} · {job.location ?? "?"}
        {job.remote && !/remote/i.test(job.location ?? "") ? " · remote" : ""}
        {formatSalary(job) ? ` · ${formatSalary(job)}` : ""}
      </p>
      <SaveButton jobId={job.id} />

      <CopilotPanel jobId={job.id} />

      <h2>Seen on</h2>
      {job.postings.map((posting) => (
        <div key={posting.id} className="card row spread">
          <span>
            <strong>{posting.source}</strong>{" "}
            <span className="muted">
              first seen {new Date(posting.first_seen).toLocaleDateString()},
              last seen {new Date(posting.last_seen).toLocaleDateString()}
            </span>
          </span>
          <a href={posting.url} target="_blank" rel="noreferrer">
            View ↗
          </a>
        </div>
      ))}

      <h2>Description</h2>
      <div className="card">
        <pre className="description">{job.description ?? "No description captured."}</pre>
      </div>
    </>
  );
}
