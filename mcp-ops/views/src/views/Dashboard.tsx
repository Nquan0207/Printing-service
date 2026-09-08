import { useEffect, useState } from "react";
import { Button, Group, Paper, SimpleGrid, Table, Text } from "@mantine/core";
import { AreaChart, BarChart, ChartCard, Empty, RowChart } from "../components/Charts";
import { ErrorPanel, Shell } from "../components/Shell";
import { createApp, readResult } from "../lib/mcp";
import { shortDate, yen } from "../lib/format";
import { SERIES_PRICE } from "../lib/palette";

/** Shape returned by GET /api/v1/admin/stats, via the get_dashboard tool. */
type Stats = {
  totals?: {
    products: number; active_products: number; categories: number; sizes: number;
    images: number; users: number; orders: number; revenue_jpy: number;
    open_cart_lines: number; cancelled_orders: number;
  };
  products_by_category?: { slug: string; name: string; count: number }[];
  orders_by_day?: { date: string; orders: number; revenue_jpy: number }[];
  top_products?: { product_id: number; product_name: string; quantity: number; revenue_jpy: number }[];
  price_buckets?: { label: string; count: number }[];
  error?: { code: string; message: string };
};

const app = createApp("Stockroom ops");
const RANGES = [7, 14, 30, 90];

function Tile({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <Paper p="sm" radius="md">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600} style={{ letterSpacing: ".05em" }}>
        {label}
      </Text>
      <Text fz={20} fw={700} mt={2}>{value}</Text>
      {hint && <Text size="xs" c="dimmed">{hint}</Text>}
    </Paper>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // The host pushes the first result when it renders the View.
    app.ontoolresult = (result: unknown) => setStats(readResult<Stats>(result));
    app.connect();
  }, []);

  // Range buttons call the tool again from inside the iframe -- no model round trip.
  async function pick(next: number) {
    setDays(next);
    setLoading(true);
    try {
      const result = await app.callServerTool({ name: "get_dashboard", arguments: { days: next } });
      setStats(readResult<Stats>(result));
    } finally {
      setLoading(false);
    }
  }

  if (!stats) return <Shell title="Stockroom operations" sub="Loading…">{null}</Shell>;
  if (stats.error) {
    return (
      <Shell title="Stockroom operations" sub="Could not load figures">
        <ErrorPanel error={stats.error} />
      </Shell>
    );
  }

  const t = stats.totals;
  if (!t) return <Shell title="Stockroom operations" sub=""><Text size="sm" c="dimmed">No data returned.</Text></Shell>;

  const cats = stats.products_by_category ?? [];
  const byDay = stats.orders_by_day ?? [];
  const top = stats.top_products ?? [];
  const buckets = stats.price_buckets ?? [];

  const bar = (
    <Group gap={4}>
      {RANGES.map((d) => (
        <Button key={d} size="compact-xs" variant={d === days ? "light" : "default"}
          color={d === days ? "raksul" : "gray"} onClick={() => pick(d)} disabled={loading}>
          {d}d
        </Button>
      ))}
    </Group>
  );

  return (
    <Shell
      title="Stockroom operations"
      sub={loading ? "Loading…" : `${t.products} products · ${t.categories} categories · last ${days} days`}
      bar={bar}
    >
      <SimpleGrid cols={{ base: 2, sm: 3, md: 6 }} spacing="xs">
        <Tile label="Revenue" value={yen(t.revenue_jpy)} hint="cancelled excluded" />
        <Tile label="Orders" value={t.orders} hint={`${t.cancelled_orders} cancelled`} />
        <Tile label="Products" value={t.products} hint={`${t.active_products} active`} />
        <Tile label="Users" value={t.users} hint={`${t.open_cart_lines} open cart lines`} />
        <Tile label="Categories" value={t.categories} hint={cats[0] ? `top: ${cats[0].name}` : undefined} />
        <Tile label="Sizes" value={t.sizes} hint={`${t.images} images`} />
      </SimpleGrid>

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="xs">
        <ChartCard title="Revenue per day">
          <AreaChart points={byDay.map((d) => ({ label: shortDate(d.date), value: d.revenue_jpy }))} />
        </ChartCard>
        <ChartCard title="Orders per day">
          <BarChart points={byDay.map((d) => ({
            label: shortDate(d.date),
            value: d.orders,
            hint: `${d.orders} order${d.orders === 1 ? "" : "s"} · ${yen(d.revenue_jpy)}`,
          }))} />
        </ChartCard>
        <ChartCard title="Products per category">
          <RowChart points={cats.map((c) => ({ label: c.name, value: c.count }))} />
        </ChartCard>
        <ChartCard title="Unit price distribution">
          <BarChart color={SERIES_PRICE}
            points={buckets.map((b) => ({ label: b.label, value: b.count, hint: `${b.count} sizes` }))} />
        </ChartCard>
      </SimpleGrid>

      <ChartCard title="Top products by revenue">
        {top.length === 0 ? (
          <Empty message="Nothing sold in this range." />
        ) : (
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Product</Table.Th>
                <Table.Th ta="right">Units</Table.Th>
                <Table.Th ta="right">Revenue</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {top.map((p) => (
                <Table.Tr key={p.product_id}>
                  <Table.Td>{p.product_name}</Table.Td>
                  <Table.Td ta="right">{p.quantity}</Table.Td>
                  <Table.Td ta="right">{yen(p.revenue_jpy)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </ChartCard>
    </Shell>
  );
}
