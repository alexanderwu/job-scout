import { SalaryChart } from "@/components/SalaryChart";
import { SkillTrendChart } from "@/components/SkillTrendChart";
import { ApiError, getSalaryInsights, getSkillTrends } from "@/lib/api";

export default async function InsightsPage({
  searchParams,
}: {
  searchParams: Promise<{ role?: string; location?: string; group_by?: string }>;
}) {
  const { role, location, group_by: groupByParam } = await searchParams;
  const groupBy = groupByParam === "location" ? "location" : "title";

  return (
    <div className="space-y-10">
      <div>
        <h1 className="mb-2 text-lg font-semibold">Market Insights</h1>
        <p className="mb-4 text-sm text-neutral-500">
          What&apos;s paying right now and which skills are trending, computed from your own
          ingested postings.
        </p>
        <form method="GET" className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-neutral-500">
            Role
            <input
              type="text"
              name="role"
              defaultValue={role}
              placeholder="e.g. Data Engineer"
              className="min-w-0 rounded-md border border-neutral-300 bg-transparent px-3 py-1.5 text-sm dark:border-neutral-700"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-neutral-500">
            Location
            <input
              type="text"
              name="location"
              defaultValue={location}
              placeholder="e.g. Remote"
              className="min-w-0 rounded-md border border-neutral-300 bg-transparent px-3 py-1.5 text-sm dark:border-neutral-700"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-neutral-500">
            Group salary by
            <select
              name="group_by"
              defaultValue={groupBy}
              className="rounded-md border border-neutral-300 bg-transparent px-3 py-1.5 text-sm dark:border-neutral-700"
            >
              <option value="title">Title</option>
              <option value="location">Location</option>
            </select>
          </label>
          <button
            type="submit"
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
          >
            Apply
          </button>
        </form>
      </div>

      <SalarySection role={role} location={location} groupBy={groupBy} />
      <SkillTrendSection role={role} />
    </div>
  );
}

async function SalarySection({
  role,
  location,
  groupBy,
}: {
  role?: string;
  location?: string;
  groupBy: "title" | "location";
}) {
  let result;
  try {
    result = await getSalaryInsights({ groupBy, role, location, limit: 10 });
  } catch (err) {
    return <ApiUnreachable err={err} />;
  }

  return (
    <section>
      <h2 className="mb-2 font-medium">Salary by {groupBy}</h2>
      {result.groups.length === 0 ? (
        <p className="text-sm text-neutral-500">
          No postings with salary data yet — try broader filters or run{" "}
          <code>jobscout ingest</code>.
        </p>
      ) : (
        <div className="space-y-4">
          {result.overall && (
            <p className="text-sm text-neutral-500">
              Overall: ${result.overall.min_salary.toLocaleString()}&ndash;$
              {result.overall.max_salary.toLocaleString()} (avg $
              {Math.round(result.overall.avg_salary).toLocaleString()}, {result.overall.job_count}{" "}
              posting{result.overall.job_count === 1 ? "" : "s"} with salary data)
            </p>
          )}
          <SalaryChart groups={result.groups} />
          <SalaryTable groups={result.groups} />
        </div>
      )}
    </section>
  );
}

function SalaryTable({
  groups,
}: {
  groups: { group: string; job_count: number; min_salary: number; max_salary: number; avg_salary: number }[];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-neutral-500">
          <tr>
            <th className="py-1 pr-4 font-normal">Group</th>
            <th className="py-1 pr-4 font-normal">Postings</th>
            <th className="py-1 pr-4 font-normal">Range</th>
            <th className="py-1 font-normal">Average</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => (
            <tr key={group.group} className="border-t border-neutral-200 dark:border-neutral-800">
              <td className="py-1 pr-4">{group.group}</td>
              <td className="py-1 pr-4 tabular-nums">{group.job_count}</td>
              <td className="py-1 pr-4 tabular-nums">
                ${group.min_salary.toLocaleString()}&ndash;${group.max_salary.toLocaleString()}
              </td>
              <td className="py-1 tabular-nums">${Math.round(group.avg_salary).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

async function SkillTrendSection({ role }: { role?: string }) {
  let result;
  try {
    result = await getSkillTrends({ role, weeks: 12, top: 8 });
  } catch (err) {
    return <ApiUnreachable err={err} />;
  }

  return (
    <section>
      <h2 className="mb-2 font-medium">Skill trends (last {result.weeks} weeks)</h2>
      {result.trends.length === 0 ? (
        <p className="text-sm text-neutral-500">
          No recent postings to analyze yet — try a broader role or run{" "}
          <code>jobscout ingest</code>.
        </p>
      ) : (
        <div className="space-y-4">
          <SkillTrendChart trends={result.trends} />
          <SkillTrendTable trends={result.trends} />
        </div>
      )}
    </section>
  );
}

function SkillTrendTable({
  trends,
}: {
  trends: { keyword: string; points: { week_start: string; count: number }[] }[];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-neutral-500">
          <tr>
            <th className="py-1 pr-4 font-normal">Keyword</th>
            <th className="py-1 pr-4 font-normal">Total mentions</th>
            <th className="py-1 font-normal">This week</th>
          </tr>
        </thead>
        <tbody>
          {trends.map((trend) => (
            <tr key={trend.keyword} className="border-t border-neutral-200 dark:border-neutral-800">
              <td className="py-1 pr-4">{trend.keyword}</td>
              <td className="py-1 pr-4 tabular-nums">
                {trend.points.reduce((sum, point) => sum + point.count, 0)}
              </td>
              <td className="py-1 tabular-nums">{trend.points.at(-1)?.count ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ApiUnreachable({ err }: { err: unknown }) {
  if (err instanceof ApiError) {
    return (
      <p className="text-sm text-red-500">
        Can&apos;t reach the Job Scout API — is <code>jobscout serve</code> running?
      </p>
    );
  }
  throw err;
}
