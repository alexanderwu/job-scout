"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { getFeed } from "@/lib/api";

const POLL_INTERVAL_MS = 30_000;
const STORAGE_KEY = "jobscout:last-feed-check";

/** Polls GET /api/feed on an interval — the polling half of PLAN.md
 * Phase 3's "WebSocket or polling feed" for new matching jobs. */
export function FeedBanner() {
  const router = useRouter();
  const [newCount, setNewCount] = useState(0);

  const check = useCallback(async () => {
    const since = localStorage.getItem(STORAGE_KEY);
    if (!since) return;
    try {
      const feed = await getFeed(since);
      if (feed.jobs.length > 0) {
        setNewCount((count) => count + feed.jobs.length);
      }
      localStorage.setItem(STORAGE_KEY, feed.checked_at);
    } catch {
      // Backend unreachable this round — just try again next interval.
    }
  }, []);

  useEffect(() => {
    if (!localStorage.getItem(STORAGE_KEY)) {
      localStorage.setItem(STORAGE_KEY, new Date().toISOString());
    }
    const id = setInterval(check, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [check]);

  if (newCount === 0) return null;

  return (
    <div className="flex items-center justify-between gap-4 rounded-lg bg-blue-50 px-4 py-3 text-sm dark:bg-blue-950/40">
      <span>
        {newCount} new job{newCount === 1 ? "" : "s"} matching your profile
      </span>
      <button
        onClick={() => {
          setNewCount(0);
          router.refresh();
        }}
        className="font-medium text-blue-700 hover:underline dark:text-blue-300"
      >
        Refresh
      </button>
    </div>
  );
}
