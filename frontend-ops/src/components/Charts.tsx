import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Stats } from "../lib/api";

// One shared palette so every chart reads as the same system.
const INK = "#1f2933";
const GRID = "#e6e9ee";
const SERIES = ["#2f6fed", "#12b5a5", "#f0a500", "#e2574c", "#8b5cf6"];

const axis = { stroke: "#8a94a6", fontSize: 11 };
const tooltip = {
  contentStyle: { borderRadius: 8, border: `1px solid ${GRID}`, fontSize: 12 },
};

export function RevenueChart({ data }: { data: Stats["orders_by_day"] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="date" tick={axis} tickFormatter={(d: string) => d.slice(5)} />
        <YAxis tick={axis} width={64} tickFormatter={(v: number) => `¥${v.toLocaleString()}`} />
        <Tooltip {...tooltip} formatter={(v) => `¥${Number(v ?? 0).toLocaleString()}`} />
        <Line
          type="monotone"
          dataKey="revenue_jpy"
          stroke={SERIES[0]}
          strokeWidth={2}
          dot={{ r: 2 }}
          name="Revenue"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function OrdersChart({ data }: { data: Stats["orders_by_day"] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="date" tick={axis} tickFormatter={(d: string) => d.slice(5)} />
        <YAxis tick={axis} width={32} allowDecimals={false} />
        <Tooltip {...tooltip} />
        <Bar dataKey="orders" fill={SERIES[1]} radius={[3, 3, 0, 0]} name="Orders" />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function CategoryChart({ data }: { data: Stats["products_by_category"] }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(220, data.length * 30)}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tick={axis} allowDecimals={false} />
        <YAxis type="category" dataKey="name" tick={{ ...axis, fontSize: 10 }} width={150} />
        <Tooltip {...tooltip} />
        <Bar dataKey="count" radius={[0, 3, 3, 0]} name="Products">
          {data.map((_, i) => (
            <Cell key={i} fill={SERIES[i % SERIES.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function PriceChart({ data }: { data: Stats["price_buckets"] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="label" tick={{ ...axis, fontSize: 10 }} />
        <YAxis tick={axis} width={32} allowDecimals={false} />
        <Tooltip {...tooltip} />
        <Bar dataKey="count" fill={SERIES[3]} radius={[3, 3, 0, 0]} name="Sizes" />
      </BarChart>
    </ResponsiveContainer>
  );
}

export const chartInk = INK;
