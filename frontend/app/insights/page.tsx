/**
 * Market insights (Phase 5) — a server component: pure reads over the
 * corpus, filters passed as URL query params so views are linkable
 * ("?role=data+engineer"). Answers two questions from your OWN
 * ingested data: what does this role pay, and which skills are
 * trending. The sample-size captions keep it honest — this is your
 * corpus, not a market survey.
 */

import Sparkline from "@/components/Sparkline";
import { insights } from "@/lib/api";

export const dynamic = "force-dynamic";

function money(n: number | null): string {
  return n === null ? "–" : `$${Math.round(n / 1000)}k`;
}

export default async function InsightsPage({
  searchParams,
}: {
  searchParams: Promise<{ role?: string; location?: string }>;
}) {
  const { role, location } = await searchParams;
  const [salary, skills] = await Promise.all([
    insights.salary({ role, location }),
    insights.skills({ role, weeks: 8 }),
  ]);

  return (
    <>
      <h1>Market insights</h1>
      <form className="row" action="/insights" method="get">
        <input type="text" name="role" placeholder="Role, e.g. data engineer" defaultValue={role} />
        <input type="text" name="location" placeholder="Location contains…" defaultValue={location} />
        <button type="submit">Filter</button>
      </form>

      <h2>What {role ? `“${role}”` : "these roles"} pay</h2>
      <p className="muted">
        From the {salary.overall.count} ingested posting
        {salary.overall.count === 1 ? "" : "s"} with salary data
        {role ? ` matching “${role}”` : ""} — your corpus, not a market survey.
      </p>
      <div className="card row" style={{ gap: "2.5rem" }}>
        <div>
          <div className="muted">25th percentile</div>
          <strong style={{ fontSize: "1.4rem" }}>{money(salary.overall.p25)}</strong>
        </div>
        <div>
          <div className="muted">median</div>
          <strong style={{ fontSize: "1.4rem" }}>{money(salary.overall.median)}</strong>
        </div>
        <div>
          <div className="muted">75th percentile</div>
          <strong style={{ fontSize: "1.4rem" }}>{money(salary.overall.p75)}</strong>
        </div>
      </div>

      {salary.by_location.length > 0 && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>By location</h2>
          {salary.by_location.map(({ location: loc, stats }) => (
            <div key={loc} className="row spread" style={{ margin: "0.4rem 0" }}>
              <span style={{ minWidth: "12rem" }}>{loc}</span>
              <span className="muted">
                {money(stats.p25)} · <strong>{money(stats.median)}</strong> ·{" "}
                {money(stats.p75)} <span className="muted">({stats.count})</span>
              </span>
            </div>
          ))}
        </div>
      )}

      <h2>Skills in demand (last {skills.weeks} weeks)</h2>
      <p className="muted">
        Share of {skills.sampled_jobs} posting{skills.sampled_jobs === 1 ? "" : "s"}
        {role ? ` matching “${role}”` : ""} mentioning each skill, week by week.
      </p>
      <div className="card">
        {skills.skills.length === 0 && (
          <p className="muted">No postings in the window — run ingestion first.</p>
        )}
        {skills.skills.map((t) => (
          <div key={t.skill} className="row spread" style={{ margin: "0.4rem 0" }}>
            <span style={{ minWidth: "10rem" }}>
              <span className="chip">{t.skill}</span>
            </span>
            <Sparkline values={t.weekly.map((w) => w.count)} />
            <span className="muted" style={{ minWidth: "6rem", textAlign: "right" }}>
              {t.total} posting{t.total === 1 ? "" : "s"}
            </span>
          </div>
        ))}
      </div>
    </>
  );
}
