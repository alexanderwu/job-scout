"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SkillTrend } from "@/lib/api";

// Fixed categorical slot order (validated for CVD separation) — never
// cycled or reassigned by rank, so a keyword keeps its color across
// re-renders as long as its position in `trends` is stable.
const SERIES_COLORS = [
  "var(--chart-series-1)",
  "var(--chart-series-2)",
  "var(--chart-series-3)",
  "var(--chart-series-4)",
  "var(--chart-series-5)",
  "var(--chart-series-6)",
  "var(--chart-series-7)",
  "var(--chart-series-8)",
];

function formatWeek(value: unknown): string {
  const date = new Date(String(value));
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

interface Row {
  week_start: string;
  [keyword: string]: string | number;
}

function toRows(trends: SkillTrend[]): Row[] {
  const weeks = trends[0]?.points.map((point) => point.week_start) ?? [];
  return weeks.map((week, i) => {
    const row: Row = { week_start: week };
    for (const trend of trends) {
      row[trend.keyword] = trend.points[i].count;
    }
    return row;
  });
}

export function SkillTrendChart({ trends }: { trends: SkillTrend[] }) {
  const rows = toRows(trends);
  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={rows} margin={{ left: 8, right: 8 }}>
        <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
        <XAxis
          dataKey="week_start"
          tickFormatter={formatWeek}
          stroke="var(--chart-axis)"
          tick={{ fill: "var(--chart-muted)", fontSize: 12 }}
        />
        <YAxis
          allowDecimals={false}
          stroke="var(--chart-axis)"
          tick={{ fill: "var(--chart-muted)", fontSize: 12 }}
        />
        <Tooltip
          labelFormatter={formatWeek}
          contentStyle={{
            background: "var(--chart-surface)",
            border: "1px solid var(--chart-grid)",
            borderRadius: 6,
            fontSize: 12,
          }}
          itemStyle={{ padding: 0 }}
        />
        <Legend wrapperStyle={{ fontSize: 12, color: "var(--chart-muted)" }} />
        {trends.map((trend, i) => (
          <Line
            key={trend.keyword}
            type="linear"
            dataKey={trend.keyword}
            stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
            strokeWidth={2}
            dot={{ r: 4, strokeWidth: 2, stroke: "var(--chart-surface)" }}
            activeDot={{ r: 6 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
