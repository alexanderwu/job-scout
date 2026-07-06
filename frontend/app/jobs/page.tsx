/**
 * Browse recent jobs — a server component: pure read, rendered on the
 * server per request (the SSR path of the app; view-source shows real
 * content, no client JS needed for this page beyond the search form,
 * which is plain HTML GET navigation).
 */

import Link from "next/link";
import { api, formatSalary } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function JobsPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const jobs = await api.listJobs({ q, hours: 24 * 45 });

  return (
    <>
      <h1>Recent jobs</h1>
      <form className="row" action="/jobs" method="get">
        <input type="text" name="q" placeholder="Search title/company…" defaultValue={q} />
        <button type="submit">Search</button>
      </form>
      {jobs.length === 0 && (
        <p className="muted">
          Nothing here yet — run <code>jobscout ingest</code> to pull postings.
        </p>
      )}
      {jobs.map((job) => (
        <div key={job.id} className="card">
          <h2 style={{ margin: 0 }}>
            <Link href={`/jobs/${job.id}`}>{job.title}</Link>
          </h2>
          <div className="muted">
            {job.company ?? "?"} · {job.location ?? "?"}
            {job.remote && !/remote/i.test(job.location ?? "") ? " · remote" : ""}
            {formatSalary(job) ? ` · ${formatSalary(job)}` : ""}
            {" · first seen "}
            {new Date(job.first_seen).toLocaleDateString()}
          </div>
        </div>
      ))}
    </>
  );
}
