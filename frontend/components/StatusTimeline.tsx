import type { SavedJob } from "@/lib/api";

const STEPS: { key: keyof SavedJob; label: string }[] = [
  { key: "created_at", label: "saved" },
  { key: "applied_at", label: "applied" },
  { key: "interviewing_at", label: "interviewing" },
  { key: "rejected_at", label: "rejected" },
  { key: "offer_at", label: "offer" },
];

export function StatusTimeline({ saved }: { saved: SavedJob }) {
  const steps = STEPS.filter((step) => saved[step.key])
    .map((step) => ({ ...step, date: new Date(saved[step.key] as string) }))
    .sort((a, b) => a.date.getTime() - b.date.getTime());

  if (steps.length === 0) return null;

  return (
    <ol className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-neutral-500">
      {steps.map((step, index) => (
        <li key={step.key}>
          {index > 0 && "→ "}
          {step.label} {step.date.toLocaleDateString()}
        </li>
      ))}
    </ol>
  );
}
