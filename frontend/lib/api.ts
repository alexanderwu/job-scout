/**
 * Typed client for the Phase 3 FastAPI backend (see
 * backend/src/jobscout/api/). Hand-written to mirror
 * backend/src/jobscout/api/schemas.py rather than generated, since the
 * surface is small and stable.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, { ...init, cache: "no-store" });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(`${init?.method ?? "GET"} ${path} failed: ${res.status} ${body}`, res.status);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export type SavedStatus = "saved" | "applied" | "interviewing" | "rejected" | "offer";

export const SAVED_STATUSES: SavedStatus[] = [
  "saved",
  "applied",
  "interviewing",
  "rejected",
  "offer",
];

export interface JobSummary {
  id: number;
  title: string;
  company: string | null;
  location: string | null;
  posted_at: string | null;
  first_seen: string;
  canonical_url: string | null;
}

export interface JobDetail extends JobSummary {
  description: string | null;
  saved_status: SavedStatus | null;
}

export interface MatchResult {
  job: JobSummary;
  score: number;
  matched_keywords: string[];
}

export interface FeedItem {
  job: JobSummary;
  score: number | null;
  matched_keywords: string[];
}

export interface FeedResponse {
  checked_at: string;
  jobs: FeedItem[];
}

export interface ProfileStatus {
  has_profile: boolean;
  updated_at: string | null;
  resume_preview: string | null;
}

export interface SavedJob {
  job: JobSummary;
  status: SavedStatus;
  created_at: string;
  updated_at: string;
}

export function getJobs(params?: { location?: string; limit?: number; offset?: number }) {
  const query = new URLSearchParams();
  if (params?.location) query.set("location", params.location);
  if (params?.limit != null) query.set("limit", String(params.limit));
  if (params?.offset != null) query.set("offset", String(params.offset));
  const qs = query.toString();
  return apiFetch<JobSummary[]>(`/api/jobs${qs ? `?${qs}` : ""}`);
}

export function getJob(jobId: number) {
  return apiFetch<JobDetail>(`/api/jobs/${jobId}`);
}

export function getProfile() {
  return apiFetch<ProfileStatus>("/api/profile");
}

export function uploadResume(file: File) {
  const form = new FormData();
  form.append("resume", file);
  return apiFetch<ProfileStatus>("/api/profile", { method: "POST", body: form });
}

export function getMatches(params?: { location?: string; limit?: number }) {
  const query = new URLSearchParams();
  if (params?.location) query.set("location", params.location);
  if (params?.limit != null) query.set("limit", String(params.limit));
  const qs = query.toString();
  return apiFetch<MatchResult[]>(`/api/matches${qs ? `?${qs}` : ""}`);
}

export function getFeed(since: string, location?: string) {
  const query = new URLSearchParams({ since });
  if (location) query.set("location", location);
  return apiFetch<FeedResponse>(`/api/feed?${query.toString()}`);
}

export function getSaved() {
  return apiFetch<SavedJob[]>("/api/saved");
}

export function saveJob(jobId: number, status: SavedStatus = "saved") {
  return apiFetch<SavedJob>(`/api/jobs/${jobId}/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
}

export function updateSavedStatus(jobId: number, status: SavedStatus) {
  return apiFetch<SavedJob>(`/api/jobs/${jobId}/save`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
}

export function unsaveJob(jobId: number) {
  return apiFetch<void>(`/api/jobs/${jobId}/save`, { method: "DELETE" });
}
