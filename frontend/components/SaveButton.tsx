"use client";

/** The one interactive element on the (otherwise server-rendered)
 * job detail page — an island, in React Server Components terms. */

import { useState } from "react";
import { api } from "@/lib/api";

export default function SaveButton({ jobId }: { jobId: number }) {
  const [saved, setSaved] = useState(false);

  return (
    <button
      className="secondary"
      disabled={saved}
      onClick={async () => {
        try {
          await api.saveJob(jobId);
          setSaved(true);
        } catch (e) {
          alert(String(e));
        }
      }}
    >
      {saved ? "Saved ✓" : "Save to tracker"}
    </button>
  );
}
