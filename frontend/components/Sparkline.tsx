/**
 * A dependency-free SVG sparkline. A charting library would ship tens
 * of kilobytes to draw what is, for a trend-at-a-glance, one polyline.
 * Server-renderable (no hooks) so insight pages stay SSR.
 */

export default function Sparkline({
  values,
  width = 140,
  height = 28,
}: {
  values: number[];
  width?: number;
  height?: number;
}) {
  if (values.length === 0) return null;
  const max = Math.max(...values, 1);
  const stepX = width / Math.max(values.length - 1, 1);
  const pad = 2;
  const points = values
    .map(
      (v, i) =>
        `${(i * stepX).toFixed(1)},${(height - pad - (v / max) * (height - pad * 2)).toFixed(1)}`,
    )
    .join(" ");
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`trend: ${values.join(", ")}`}
    >
      <polyline
        points={points}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
