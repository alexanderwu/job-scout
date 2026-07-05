import { FeedBanner } from "@/components/FeedBanner";
import { JobCard } from "@/components/JobCard";
import { ResumeUpload } from "@/components/ResumeUpload";
import { getMatches, getProfile } from "@/lib/api";

export default async function HomePage() {
  let profile;
  try {
    profile = await getProfile();
  } catch {
    return (
      <p className="text-sm text-red-500">
        Can&apos;t reach the Job Scout API — is <code>jobscout serve</code> running?
      </p>
    );
  }

  const matches = profile.has_profile ? await getMatches().catch(() => []) : [];

  return (
    <div className="space-y-8">
      <FeedBanner />

      <section>
        <h2 className="mb-2 text-lg font-semibold">Resume</h2>
        <ResumeUpload compact={profile.has_profile} />
        {profile.has_profile && (
          <p className="mt-2 text-sm text-neutral-500">
            Using the resume uploaded {new Date(profile.updated_at!).toLocaleString()}
            {profile.resume_preview && <> — &ldquo;{profile.resume_preview}…&rdquo;</>}
          </p>
        )}
      </section>

      {profile.has_profile && (
        <section>
          <h2 className="mb-2 text-lg font-semibold">Matches</h2>
          {matches.length === 0 ? (
            <p className="text-sm text-neutral-500">
              No ranked jobs yet — run <code>jobscout ingest</code> and <code>jobscout embed</code>{" "}
              to populate the corpus.
            </p>
          ) : (
            <div className="space-y-3">
              {matches.map((match) => (
                <JobCard
                  key={match.job.id}
                  job={match.job}
                  score={match.score}
                  matchedKeywords={match.matched_keywords}
                />
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
