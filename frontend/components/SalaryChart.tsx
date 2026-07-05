"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SalaryGroup } from "@/lib/api";

function formatCompact(value: number): string {
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(
    value,
  );
}

function SalaryTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: SalaryGroup }[];
}) {
  if (!active || !payload?.length) return null;
  const group = payload[0].payload;
  return (
    <div className="rounded-md border border-neutral-200 bg-white px-3 py-2 text-xs shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
      <p className="font-medium text-neutral-900 dark:text-neutral-100">{group.group}</p>
      <p className="text-neutral-500">
        avg <span className="font-semibold text-neutral-900 dark:text-neutral-100">
          ${formatCompact(group.avg_salary)}
        </span>
      </p>
      <p className="text-neutral-500">
        range ${formatCompact(group.min_salary)}&ndash;${formatCompact(group.max_salary)}
      </p>
      <p className="text-neutral-500">
        {group.job_count} posting{group.job_count === 1 ? "" : "s"} with salary data
      </p>
    </div>
  );
}

export function SalaryChart({ groups }: { groups: SalaryGroup[] }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(groups.length * 40, 120)}>
      <BarChart data={groups} layout="vertical" margin={{ left: 8, right: 24 }}>
        <CartesianGrid horizontal={false} stroke="var(--chart-grid)" />
        <XAxis
          type="number"
          tickFormatter={formatCompact}
          stroke="var(--chart-axis)"
          tick={{ fill: "var(--chart-muted)", fontSize: 12 }}
        />
        <YAxis
          type="category"
          dataKey="group"
          width={140}
          stroke="var(--chart-axis)"
          tick={{ fill: "var(--chart-muted)", fontSize: 12 }}
        />
        <Tooltip content={<SalaryTooltip />} cursor={{ fill: "var(--chart-grid)" }} />
        <Bar dataKey="avg_salary" fill="var(--chart-series-1)" radius={[0, 4, 4, 0]} maxBarSize={24} />
      </BarChart>
    </ResponsiveContainer>
  );
}
