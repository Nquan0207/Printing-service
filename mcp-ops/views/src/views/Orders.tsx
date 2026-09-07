import { useEffect, useRef, useState } from "react";
import { Button, Group, Table, Text, TextInput } from "@mantine/core";
import { AdminGate, isAuthRequired } from "../components/AdminGate";
import { ErrorPanel, Shell, StatusPill } from "../components/Shell";
import { createApp, readResult } from "../lib/mcp";
import { asDate, yen } from "../lib/format";

type Item = { product_name: string; size_name: string; quantity: number; subtotal_jpy: number };
type Order = {
  order_number: string; status: string; total_jpy: number; created_at: string;
  user_name: string; user_email: string; shipping_address: string;
  items: Item[]; item_count: number; total_quantity: number;
};
/** What the server actually filtered on. Absent keys mean "not filtered".
 *  The panel renders itself from this rather than from what it believes it
 *  sent, so a prompt-driven filter and a typed one land in the same place --
 *  which is what makes the controls arrive pre-filled. */
type Applied = {
  q?: string;
  statuses?: string[];
  min_total?: number; max_total?: number;
  min_quantity?: number; max_quantity?: number;
  from?: string; to?: string;
};
type Payload = { orders?: Order[]; total?: number; applied?: Applied };

const STATUSES = ["pending", "confirmed", "cancelled"] as const;
/** Field id -> the tool argument it fills. */
const FIELDS = {
  q: "q",
  min_total: "min_total", max_total: "max_total",
  min_quantity: "min_quantity", max_quantity: "max_quantity",
  from: "date_from", to: "date_to",
} as const;
type Field = keyof typeof FIELDS;

const app = createApp("Orders");

function toArgs(applied: Applied): Record<string, unknown> {
  const a: Record<string, unknown> = {};
  if (applied.statuses?.length) a.status = applied.statuses.join(",");
  for (const [id, arg] of Object.entries(FIELDS) as [Field, string][]) {
    const value = applied[id];
    if (value !== undefined && value !== "" && value !== 0) a[arg] = value;
  }
  return a;
}

export default function Orders() {
  const [data, setData] = useState<(Payload & { error?: { code: string; message: string } }) | null>(null);
  const [applied, setApplied] = useState<Applied>({});
  const [loading, setLoading] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    app.ontoolresult = (r: unknown) => {
      const payload = readResult<Payload>(r);
      setData(payload);
      setApplied(payload.applied ?? {});
    };
    app.connect();
  }, []);

  async function refetch(next: Applied) {
    setApplied(next);
    setLoading(true);
    try {
      const r = await app.callServerTool({ name: "list_orders", arguments: toArgs(next) });
      const payload = readResult<Payload>(r);
      setData(payload);
      // The server is the authority on what was applied.
      setApplied(payload.applied ?? {});
    } finally {
      setLoading(false);
    }
  }

  /** Typing waits; picking a date or pressing a chip does not. */
  function schedule(next: Applied, delay: number) {
    setApplied(next);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => refetch(next), delay);
  }

  function setField(id: Field, raw: string) {
    const next = { ...applied };
    if (raw.trim() === "") delete next[id];
    else if (id === "q" || id === "from" || id === "to") (next[id] as string) = raw;
    else (next[id] as number) = Number(raw);
    schedule(next, id === "from" || id === "to" ? 0 : 350);
  }

  function toggleStatus(status: string) {
    window.clearTimeout(timer.current);
    if (status === "") return void refetch({}); // "All" clears everything.
    const set = new Set(applied.statuses ?? []);
    set.has(status) ? set.delete(status) : set.add(status);
    refetch({ ...applied, statuses: [...set] });
  }

  if (!data) return <Shell title="Orders" sub="Loading…">{null}</Shell>;
  if (data.error) {
    return (
      <Shell title="Orders" sub="">
        {isAuthRequired(data)
          ? <AdminGate app={app} onSignedIn={() => refetch(applied)} />
          : <ErrorPanel error={data.error} />}
      </Shell>
    );
  }

  const orders = data.orders ?? [];
  const units = orders.reduce((n, o) => n + o.total_quantity, 0);
  const value = orders.reduce((n, o) => n + o.total_jpy, 0);
  const selected = new Set(applied.statuses ?? []);
  const none = Object.keys(applied).length === 0;
  const nf = (id: Field) => (applied[id] === undefined ? "" : String(applied[id]));

  const bar = (
    <>
      <Group gap={6} mb={6}>
        <Button size="compact-xs" variant={none ? "light" : "default"} color={none ? "raksul" : "gray"}
          title="Clear every filter" onClick={() => toggleStatus("")}>All</Button>
        {STATUSES.map((s) => (
          <Button key={s} size="compact-xs" tt="none"
            variant={selected.has(s) ? "light" : "default"} color={selected.has(s) ? "raksul" : "gray"}
            onClick={() => toggleStatus(s)}>{s}</Button>
        ))}
        <TextInput size="xs" w={190} placeholder="Order # or customer…"
          value={nf("q")} onChange={(e) => setField("q", e.currentTarget.value)} />
      </Group>
      <Group gap={6}>
        <Text size="xs" c="dimmed">¥</Text>
        <TextInput size="xs" w={92} type="number" placeholder="min" value={nf("min_total")}
          onChange={(e) => setField("min_total", e.currentTarget.value)} />
        <TextInput size="xs" w={92} type="number" placeholder="max" value={nf("max_total")}
          onChange={(e) => setField("max_total", e.currentTarget.value)} />
        <Text size="xs" c="dimmed">units</Text>
        <TextInput size="xs" w={92} type="number" placeholder="min" value={nf("min_quantity")}
          onChange={(e) => setField("min_quantity", e.currentTarget.value)} />
        <TextInput size="xs" w={92} type="number" placeholder="max" value={nf("max_quantity")}
          onChange={(e) => setField("max_quantity", e.currentTarget.value)} />
        <Text size="xs" c="dimmed">placed</Text>
        <TextInput size="xs" type="date" value={nf("from")}
          onChange={(e) => setField("from", e.currentTarget.value)} />
        <TextInput size="xs" type="date" value={nf("to")}
          onChange={(e) => setField("to", e.currentTarget.value)} />
      </Group>
    </>
  );

  return (
    <Shell
      title="Orders"
      sub={loading ? "Loading…" : `${orders.length} of ${data.total ?? orders.length} orders · ${units} units · ${yen(value)}`}
      bar={bar}
    >
      {orders.length === 0 ? (
        <Text size="sm" c="dimmed">Nothing to show.</Text>
      ) : (
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Order</Table.Th><Table.Th>Customer</Table.Th>
              <Table.Th ta="right">Units / lines</Table.Th><Table.Th ta="right">Total</Table.Th>
              <Table.Th>Placed</Table.Th><Table.Th>Status</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {orders.map((o) => (
              <Table.Tr key={o.order_number}>
                <Table.Td ff="monospace" fz="xs">{o.order_number}</Table.Td>
                <Table.Td>
                  {o.user_name}
                  <Text size="xs" c="dimmed">{o.user_email}</Text>
                </Table.Td>
                {/* The line items travel with the order, so a hover reveals
                    them without another round trip. */}
                <Table.Td ta="right"
                  title={o.items.map((i) => `${i.product_name} ${i.size_name} ×${i.quantity}`).join("\n")}>
                  {o.total_quantity} <Text span c="dimmed">/ {o.item_count}</Text>
                </Table.Td>
                <Table.Td ta="right">{yen(o.total_jpy)}</Table.Td>
                <Table.Td c="dimmed">{asDate(o.created_at)}</Table.Td>
                <Table.Td><StatusPill status={o.status} /></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Shell>
  );
}
