/**
 * Typed client for the Job Scout API.
 *
 * One module owns every fetch: the response types below mirror
 * backend/src/jobscout/api/schemas.py, and if the API changes shape
 * there is exactly one file to update (a shared OpenAPI-generated
 * client would automate that — worthwhile once the schema stops
 * moving; hand-written types are clearer while learning).
 *
 * Server components call these functions directly (Node fetch);
 * client components do too (browser fetch) — NEXT_PUBLIC_ makes the
 * URL available in both runtimes.
 */

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface JobSummary {
  id: number;
  title: string;
  company: string | null;
  location: string | null;
  remote: boolean | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  first_seen: string;
  last_seen: string;
}

export interface PostingOut {
  id: number;
  source: string;
  url: string;
  posted_at: string | null;
  first_seen: string;
  last_seen: string;
}

export interface JobDetail extends JobSummary {
  description: string | null;
  postings: PostingOut[];
}

export interface Explanation {
  overlapping: string[];
  missing: string[];
  summary: string;
}

export interface Match {
  job: JobSummary;
  score: number;
  apply_url: string | null;
  explanation: Explanation;
}

export interface MatchResponse {
  resume_skills: string[];
  matches: Match[];
}

export interface Profile {
  id: number;
  name: string;
  created_at: string;
  updated_at: string;
  skills: string[];
}

export interface FeedResponse {
  since: string;
  matches: Match[];
}

export interface ApplicationEvent {
  status: string;
  at: string;
}

export interface Application {
  id: number;
  job: JobSummary;
  profile_id: number | null;
  status: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
  events: ApplicationEvent[];
}

export const APPLICATION_STATUSES = [
  "saved",
  "applied",
  "interviewing",
  "offer",
  "rejected",
] as const;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    // The job list changes as ingestion runs; never serve a stale
    // Next.js data cache entry for API reads.
    cache: "no-store",
    ...init,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${body}`);
  }
  // 204 No Content has no body to parse.
  return (response.status === 204 ? undefined : response.json()) as Promise<T>;
}

export const api = {
  listJobs: (params: { q?: string; hours?: number } = {}) => {
    const search = new URLSearchParams();
    if (params.q) search.set("q", params.q);
    if (params.hours) search.set("hours", String(params.hours));
    return request<JobSummary[]>(`/jobs?${search}`);
  },

  getJob: (id: number | string) => request<JobDetail>(`/jobs/${id}`),

  listProfiles: () => request<Profile[]>("/profiles"),

  createProfile: (form: FormData) =>
    request<Profile>("/profiles", { method: "POST", body: form }),

  matchProfile: (
    profileId: number | string,
    filters: {
      location?: string;
      remote_only?: boolean;
      min_salary?: number;
    } = {},
  ) => {
    const search = new URLSearchParams();
    if (filters.location) search.set("location", filters.location);
    if (filters.remote_only) search.set("remote_only", "true");
    if (filters.min_salary) search.set("min_salary", String(filters.min_salary));
    return request<MatchResponse>(`/profiles/${profileId}/match?${search}`, {
      method: "POST",
    });
  },

  feed: (profileId: number | string, hours: number) =>
    request<FeedResponse>(`/profiles/${profileId}/feed?hours=${hours}`),

  listApplications: () => request<Application[]>("/applications"),

  saveJob: (jobId: number, profileId?: number) =>
    request<Application>("/applications", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId, profile_id: profileId ?? null }),
    }),

  updateApplication: (id: number, patch: { status?: string; notes?: string }) =>
    request<Application>(`/applications/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),

  deleteApplication: (id: number) =>
    request<void>(`/applications/${id}`, { method: "DELETE" }),
};

/** "170,000–210,000 USD" or null when a job has no salary data. */
export function formatSalary(job: JobSummary): string | null {
  if (!job.salary_min && !job.salary_max) return null;
  const fmt = (n: number) => n.toLocaleString("en-US");
  const lo = job.salary_min ? fmt(job.salary_min) : "?";
  const hi = job.salary_max ? fmt(job.salary_max) : "?";
  return `${lo}–${hi} ${job.salary_currency ?? ""}`.trim();
}

// --- Phase 4: copilot -------------------------------------------------------

export interface SkillDemand {
  skill: string;
  count: number;
  share: number;
}

export interface SkillGap {
  role: string;
  sampled_jobs: number;
  have: SkillDemand[];
  missing: SkillDemand[];
}

export interface TailorAdvice {
  job_id: number;
  suggestions: string[];
  emphasized_skills: string[];
  gap_skills: string[];
  prose: string | null;
}

export interface CoverLetter {
  job_id: number;
  body: string;
  generated_by: string;
}

export const copilot = {
  skillGap: (profileId: number | string, role: string) =>
    request<SkillGap>(
      `/profiles/${profileId}/skill-gap?role=${encodeURIComponent(role)}`,
    ),

  tailor: (jobId: number | string, profileId: number | string) =>
    request<TailorAdvice>(`/jobs/${jobId}/tailor?profile_id=${profileId}`, {
      method: "POST",
    }),

  coverLetter: (jobId: number | string, profileId: number | string) =>
    request<CoverLetter>(`/jobs/${jobId}/cover-letter?profile_id=${profileId}`, {
      method: "POST",
    }),

  reminders: (days = 7) =>
    request<Application[]>(`/applications/reminders?days=${days}`),
};
