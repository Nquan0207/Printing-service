/**
 * Inline SVG charts, as React components.
 *
 * Still no chart library. The View is inlined into one HTML file for a
 * deny-by-default iframe CSP, and Recharts would add roughly half a megabyte
 * to draw five simple shapes. These are plain SVG elements — nothing to
 * hydrate, nothing to load.
 *
 * Interactivity is a native <title> per shape: the host renders it as a
 * tooltip with no JS, no positioning maths, and no way to escape the iframe.
 */
import { Paper, Text } from "@mantine/core";
import { shortYen } from "../lib/format";
import { SERIES_CATEGORY, SERIES_ORDERS, SERIES_REVENUE } from "../lib/palette";

export type Series = { label: string; value: number; hint?: string };

const W = 560;
const H = 190;
const PAD = { top: 12, right: 10, bottom: 26, left: 52 };
const PLOT_W = W - PAD.left - PAD.right;
const PLOT_H = H - PAD.top - PAD.bottom;

/** A "nice" axis maximum, so gridlines land on 200/500/1000 rather than 187. */
function niceMax(value: number): number {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  return [1, 2, 2.5, 5, 10].find((s) => value <= s * magnitude)! * magnitude;
}

/** Every N-th label, so a 90-day range does not overprint its own axis. */
const everyNth = (count: number) => Math.max(1, Math.ceil(count / 8));

export function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Paper p="sm" radius="md">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600} mb={6} style={{ letterSpacing: ".05em" }}>
        {title}
      </Text>
      {children}
    </Paper>
  );
}

export function Empty({ message = "No data for this range." }: { message?: string }) {
  return <Text size="sm" c="dimmed" my="sm">{message}</Text>;
}

function Gridlines({ max, fmt }: { max: number; fmt: (n: number) => string }) {
  return (
    <>
      {[0, 0.25, 0.5, 0.75, 1].map((f) => {
        const y = PAD.top + PLOT_H * (1 - f);
        return (
          <g key={f}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y} y2={y}
              stroke="var(--mantine-color-default-border)" strokeWidth={1} strokeDasharray="3 3" />
            <text x={PAD.left - 6} y={y + 3} textAnchor="end"
              fill="var(--mantine-color-dimmed)" fontSize={9}>
              {fmt(max * f)}
            </text>
          </g>
        );
      })}
    </>
  );
}

function AxisLabels({ points, x }: { points: Series[]; x: (i: number) => number }) {
  const step = everyNth(points.length);
  return (
    <>
      {points.map((p, i) =>
        i % step ? null : (
          <text key={p.label + i} x={x(i)} y={H - 8} textAnchor="middle"
            fill="var(--mantine-color-dimmed)" fontSize={9}>
            {p.label}
          </text>
        ),
      )}
    </>
  );
}

/** Filled line chart -- revenue over time. */
export function AreaChart({ points, fmt = shortYen }: { points: Series[]; fmt?: (n: number) => string }) {
  if (points.length === 0) return <Empty />;
  const max = niceMax(Math.max(...points.map((p) => p.value), 1));
  const x = (i: number) =>
    PAD.left + (points.length === 1 ? PLOT_W / 2 : (PLOT_W * i) / (points.length - 1));
  const y = (v: number) => PAD.top + PLOT_H * (1 - v / max);

  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join("");
  const area = `${line}L${x(points.length - 1).toFixed(1)},${PAD.top + PLOT_H}L${x(0).toFixed(1)},${PAD.top + PLOT_H}Z`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img"
      style={{ width: "100%", height: "auto", display: "block", overflow: "visible" }}>
      <Gridlines max={max} fmt={fmt} />
      <path d={area} fill={SERIES_REVENUE} opacity={0.13} />
      <path d={line} fill="none" stroke={SERIES_REVENUE} strokeWidth={2} strokeLinejoin="round" />
      {/* Dots carry the <title>: a 1px line is far too thin to hover. */}
      {points.map((p, i) => (
        <circle key={i} cx={x(i)} cy={y(p.value)} r={7} fill="transparent">
          <title>{`${p.label} — ${p.hint ?? fmt(p.value)}`}</title>
        </circle>
      ))}
      <AxisLabels points={points} x={x} />
    </svg>
  );
}

/** Vertical bars -- orders per day, price distribution. */
export function BarChart({
  points, fmt = (n: number) => String(n), color = SERIES_ORDERS,
}: { points: Series[]; fmt?: (n: number) => string; color?: string }) {
  if (points.length === 0) return <Empty />;
  const max = niceMax(Math.max(...points.map((p) => p.value), 1));
  const slot = PLOT_W / points.length;
  const width = Math.max(3, Math.min(38, slot * 0.62));
  const cx = (i: number) => PAD.left + slot * (i + 0.5);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img"
      style={{ width: "100%", height: "auto", display: "block", overflow: "visible" }}>
      <Gridlines max={max} fmt={fmt} />
      {points.map((p, i) => {
        const h = (PLOT_H * p.value) / max;
        return (
          <g key={i}>
            <rect x={cx(i) - width / 2} y={PAD.top + PLOT_H - h} width={width}
              height={Math.max(h, 0)} rx={4} fill={color} />
            {/* Zero still gets a hover target, otherwise a quiet day is unreadable. */}
            <rect x={cx(i) - slot / 2} y={PAD.top} width={slot} height={PLOT_H} fill="transparent">
              <title>{`${p.label} — ${p.hint ?? fmt(p.value)}`}</title>
            </rect>
          </g>
        );
      })}
      <AxisLabels points={points} x={cx} />
    </svg>
  );
}

/** Horizontal bars -- category names are far too long for an x-axis. */
export function RowChart({ points, fmt = (n: number) => String(n) }: { points: Series[]; fmt?: (n: number) => string }) {
  if (points.length === 0) return <Empty />;
  const max = Math.max(...points.map((p) => p.value), 1);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5, paddingBottom: 6 }}>
      {points.map((p) => (
        <div key={p.label}
          title={`${p.label} — ${p.hint ?? fmt(p.value)}`}
          style={{
            display: "grid", gridTemplateColumns: "minmax(0,168px) 1fr 40px",
            gap: 8, alignItems: "center", fontSize: 11,
          }}>
          <span style={{
            color: "var(--mantine-color-dimmed)", overflow: "hidden",
            textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>{p.label}</span>
          <span style={{
            background: "var(--mantine-color-default-hover)", borderRadius: 3,
            height: 14, overflow: "hidden",
          }}>
            <span style={{
              display: "block", height: "100%", borderRadius: 3,
              background: SERIES_CATEGORY,
              width: `${((p.value / max) * 100).toFixed(1)}%`,
            }} />
          </span>
          <span style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
            {fmt(p.value)}
          </span>
        </div>
      ))}
    </div>
  );
}
