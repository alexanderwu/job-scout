"use client";

/**
 * Application tracker: pipeline tabs (saved → applied → interviewing →
 * offer / rejected), status changes and notes inline. Tabs + list
 * rather than a kanban board: drag-and-drop is a lot of interaction
 * code for something a <select> does in one click, and at personal
 * scale the count-per-stage tabs communicate pipeline health just as
 * well.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, copilot, Application, APPLICATION_STATUSES } from "@/lib/api";

const REMINDER_DAYS = 7;

export default function TrackerPage() {
  const [apps, setApps] = useState<Application[]>([]);
  const [stale, setStale] = useState<Application[]>([]);
  const [tab, setTab] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.listApplications().then(setApps).catch((e) => setError(String(e)));
    copilot.reminders(REMINDER_DAYS).then(setStale).catch(() => {});
  }, []);

  useEffect(load, [load]);

  async function setStatus(app: Application, status: string) {
    try {
      await api.updateApplication(app.id, { status });
      load();
    } catch (e) {
      setError(String(e));
    }
  }

  async function saveNotes(app: Application, notes: string) {
    if (notes === (app.notes ?? "")) return;
    try {
      await api.updateApplication(app.id, { notes });
      load();
    } catch (e) {
      setError(String(e));
    }
  }

  const shown = tab === "all" ? apps : apps.filter((a) => a.status === tab);
  const count = (s: string) => apps.filter((a) => a.status === s).length;
  const idleDays = (a: Application) =>
    Math.floor((Date.now() - new Date(a.updated_at).getTime()) / 86_400_000);

  return (
    <>
      <h1>Application tracker</h1>

      {stale.length > 0 && (
        <div className="banner">
          <strong>Needs a nudge:</strong>{" "}
          {stale
            .map((a) => `${a.job.title} (${a.status}, idle ${idleDays(a)}d)`)
            .join(" · ")}{" "}
          — follow up or move them along.
        </div>
      )}

      <div className="tabs">
        <button className={tab === "all" ? "active" : ""} onClick={() => setTab("all")}>
          all ({apps.length})
        </button>
        {APPLICATION_STATUSES.map((s) => (
          <button key={s} className={tab === s ? "active" : ""} onClick={() => setTab(s)}>
            {s} ({count(s)})
          </button>
        ))}
      </div>

      {error && <div className="error">{error}</div>}
      {shown.length === 0 && (
        <p className="muted">
          Nothing here. Save jobs from your <Link href="/">match list</Link>.
        </p>
      )}

      {shown.map((app) => (
        <div key={app.id} className="card">
          <div className="row spread">
            <h2 style={{ margin: 0 }}>
              <Link href={`/jobs/${app.job.id}`}>{app.job.title}</Link>{" "}
              <span className="muted">@ {app.job.company ?? "?"}</span>
            </h2>
            <select
              value={app.status}
              onChange={(e) => setStatus(app, e.target.value)}
            >
              {APPLICATION_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div className="muted">
            {app.events
              .map((e) => `${e.status} ${new Date(e.at).toLocaleDateString()}`)
              .join(" → ")}
          </div>
          <textarea
            style={{ minHeight: "3rem" }}
            placeholder="Notes (recruiter name, next step, …)"
            defaultValue={app.notes ?? ""}
            onBlur={(e) => saveNotes(app, e.target.value)}
          />
        </div>
      ))}
    </>
  );
}
