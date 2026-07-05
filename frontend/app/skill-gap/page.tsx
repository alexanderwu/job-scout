import { ApiError, getSkillGap } from "@/lib/api";

export default async function SkillGapPage({
  searchParams,
}: {
  searchParams: Promise<{ role?: string }>;
}) {
  const { role } = await searchParams;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="mb-2 text-lg font-semibold">Skill Gap</h1>
        <p className="mb-4 text-sm text-neutral-500">
          See which keywords a target role&apos;s postings ask for that your resume doesn&apos;t
          mention yet.
        </p>
        <form method="GET" className="flex flex-wrap gap-3">
          <input
            type="text"
            name="role"
            defaultValue={role}
            placeholder="e.g. Data Engineer"
            className="min-w-0 flex-1 rounded-md border border-neutral-300 bg-transparent px-3 py-1.5 text-sm dark:border-neutral-700"
          />
          <button
            type="submit"
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
          >
            Analyze
          </button>
        </form>
      </div>

      {role && <SkillGapResults role={role} />}
    </div>
  );
}

async function SkillGapResults({ role }: { role: string }) {
  let result;
  try {
    result = await getSkillGap(role);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return (
        <p className="text-sm text-neutral-500">
          Upload a resume first — skill-gap analysis compares it against postings.
        </p>
      );
    }
    return (
      <p className="text-sm text-red-500">
        Can&apos;t reach the Job Scout API — is <code>jobscout serve</code> running?
      </p>
    );
  }

  if (result.postings_considered === 0) {
    return (
      <p className="text-sm text-neutral-500">
        No postings matched &ldquo;{role}&rdquo; yet — try a broader title or run{" "}
        <code>jobscout ingest</code>.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-neutral-500">
        Based on {result.postings_considered} posting{result.postings_considered === 1 ? "" : "s"}{" "}
        matching &ldquo;{role}&rdquo;.
      </p>

      <section>
        <h2 className="mb-2 font-medium">Missing from your resume</h2>
        {result.missing_keywords.length === 0 ? (
          <p className="text-sm text-neutral-500">No gaps found — nice.</p>
        ) : (
          <KeywordList entries={result.missing_keywords} />
        )}
      </section>

      <section>
        <h2 className="mb-2 font-medium">Already covered</h2>
        {result.matched_keywords.length === 0 ? (
          <p className="text-sm text-neutral-500">No overlap yet.</p>
        ) : (
          <KeywordList entries={result.matched_keywords} />
        )}
      </section>
    </div>
  );
}

function KeywordList({ entries }: { entries: { keyword: string; count: number }[] }) {
  return (
    <ul className="flex flex-wrap gap-2">
      {entries.map((entry) => (
        <li
          key={entry.keyword}
          className="rounded-full border border-neutral-200 px-3 py-1 text-xs dark:border-neutral-800"
        >
          {entry.keyword} <span className="text-neutral-500">· {entry.count}</span>
        </li>
      ))}
    </ul>
  );
}
