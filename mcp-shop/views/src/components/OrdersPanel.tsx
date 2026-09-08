import { useEffect, useState } from "react";
import {
  Accordion, Badge, Box, Button, Group, Paper, Stack, Table, Text, Title,
} from "@mantine/core";
import { callTool } from "../lib/mcp";
import { Identify } from "./Identify";
import { STATUS_COLOR, shortDate, yen } from "../lib/format";

type Item = {
  product_name: string; size_name: string; quantity: number;
  unit_price_jpy: number; subtotal_jpy: number;
};
type Order = {
  order_number: string; status: string; shipping_address: string;
  total_jpy: number; created_at: string; items: Item[];
};
export type Payload = {
  orders?: Order[];
  total?: number;
  user?: { name: string; email: string } | null;
  error?: { code: string; message: string };
};

/**
 * Order history, without any bridge wiring.
 *
 * Rendered standalone by the orders View and inline by the storefront, so it
 * owns its data but not the connection -- two `app.connect()` calls in one
 * iframe would be two handshakes for one host.
 */
export function OrdersPanel({ seed }: { seed?: Payload | null }) {
  const [data, setData] = useState<Payload | null>(seed ?? null);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setData(await callTool<Payload>("order_history", { limit: 20 }));
    } catch (e) {
      // callTool throws on an error envelope, so recover the shape the panel
      // renders from -- most often "you are still a guest".
      const message = e instanceof Error ? e.message : String(e);
      setData({ error: { code: /sign|email/i.test(message) ? "identity_required" : "error", message } });
    } finally {
      setLoading(false);
    }
  }

  // A seed arrives when the host pushed a tool result; otherwise fetch.
  useEffect(() => { if (seed) setData(seed); }, [seed]);
  useEffect(() => { if (!seed) void load(); }, []);

  if (!data) return <Box p="md"><Text size="sm" c="dimmed">Loading…</Text></Box>;

  if (data.error) {
    return (
      <Box p="md">
        <Title order={1} size="h4" mb="xs">Your orders</Title>
        {data.error.code === "identity_required" ? (
          <Identify
            title="Which email did you order with?"
            hint="Your orders are attached to the address you checked out with."
            onSignedIn={load}
          />
        ) : (
          <Text size="sm" c="red">{data.error.message}</Text>
        )}
      </Box>
    );
  }

  const orders = data.orders ?? [];
  const spent = orders.reduce((n, o) => n + (o.status === "cancelled" ? 0 : o.total_jpy), 0);

  return (
    <Box p="md">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Title order={1} size="h4">Your orders</Title>
        <Button size="compact-xs" variant="subtle" loading={loading} onClick={load}>
          Refresh
        </Button>
      </Group>
      <Text size="xs" c="dimmed" mb="sm">
        {orders.length} of {data.total ?? orders.length}
        {data.user ? ` · ${data.user.email}` : ""}
        {orders.length ? ` · ${yen(spent)} spent` : ""}
      </Text>

      {orders.length === 0 ? (
        <Text size="sm" c="dimmed">No orders yet.</Text>
      ) : (
        // Collapsed by default: the line items travel with every order, so
        // opening one costs nothing, and twenty expanded orders is a wall.
        <Accordion variant="separated" radius="md">
          {orders.map((o) => (
            <Accordion.Item key={o.order_number} value={o.order_number}>
              <Accordion.Control>
                <Group justify="space-between" wrap="nowrap" pr="sm">
                  <Stack gap={0}>
                    <Text size="sm" ff="monospace">{o.order_number}</Text>
                    <Text size="xs" c="dimmed">
                      {shortDate(o.created_at)} · {o.items.length} line{o.items.length === 1 ? "" : "s"}
                    </Text>
                  </Stack>
                  <Group gap="xs" wrap="nowrap">
                    <Text size="sm" fw={700}>{yen(o.total_jpy)}</Text>
                    <Badge size="sm" variant="light" tt="none"
                           color={STATUS_COLOR[o.status] ?? "gray"}>
                      {o.status}
                    </Badge>
                  </Group>
                </Group>
              </Accordion.Control>
              <Accordion.Panel>
                <Table fz="xs" withRowBorders={false}>
                  <Table.Tbody>
                    {o.items.map((it, i) => (
                      <Table.Tr key={i}>
                        <Table.Td>{it.product_name}</Table.Td>
                        <Table.Td c="dimmed">{it.size_name}</Table.Td>
                        <Table.Td ta="right">×{it.quantity}</Table.Td>
                        <Table.Td ta="right">{yen(it.subtotal_jpy)}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
                <Paper p="xs" mt="xs" radius="sm" bg="var(--mantine-color-default)">
                  <Text size="xs" c="dimmed">Ships to {o.shipping_address}</Text>
                </Paper>
              </Accordion.Panel>
            </Accordion.Item>
          ))}
        </Accordion>
      )}
    </Box>
  );
}
