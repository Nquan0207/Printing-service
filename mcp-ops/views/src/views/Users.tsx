import { useEffect, useRef, useState } from "react";
import { Badge, Button, Group, Table, Text, TextInput } from "@mantine/core";
import { AdminGate, isAuthRequired } from "../components/AdminGate";
import { ErrorPanel, Shell } from "../components/Shell";
import { createApp, readResult } from "../lib/mcp";
import { asDate, yen } from "../lib/format";

type User = {
  id: number; name: string; email: string; created_at: string; is_admin: boolean;
  cart_lines: number; orders: number; spent_jpy: number;
};
/** The same contract as the order list: the panel renders itself from what the
 *  server says it filtered on, which is what makes the controls arrive
 *  pre-filled from the prompt. */
type Applied = {
  q?: string; role?: "admin" | "customer"; has_cart?: boolean;
  min_orders?: number; max_orders?: number;
  min_spent?: number; max_spent?: number;
  from?: string; to?: string;
};
type Payload = { users?: User[]; total?: number; applied?: Applied };

const FIELDS = {
  q: "q",
  min_orders: "min_orders", max_orders: "max_orders",
  min_spent: "min_spent", max_spent: "max_spent",
  from: "date_from", to: "date_to",
} as const;
type Field = keyof typeof FIELDS;

const app = createApp("Users");

function toArgs(applied: Applied): Record<string, unknown> {
  const a: Record<string, unknown> = {};
  if (applied.role) a.role = applied.role;
  if (applied.has_cart) a.has_cart = true;
  for (const [id, arg] of Object.entries(FIELDS) as [Field, string][]) {
    const value = applied[id];
    if (value === undefined || value === "") continue;
    // 0 is a real filter on orders ("never ordered"), so it must survive here
    // even though 0 means "unset" for every money field.
    if (value === 0 && id !== "max_orders" && id !== "min_orders") continue;
    a[arg] = value;
  }
  return a; // an omitted max_orders falls through to the tool's -1 = "no maximum"
}

export default function Users() {
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
      const r = await app.callServerTool({ name: "list_users", arguments: toArgs(next) });
      const payload = readResult<Payload>(r);
      setData(payload);
      setApplied(payload.applied ?? {});
    } finally {
      setLoading(false);
    }
  }

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

  function pickRole(role: "" | "admin" | "customer") {
    window.clearTimeout(timer.current);
    if (role === "") return void refetch({}); // "All" clears everything, not just the role.
    // Roles are mutually exclusive; clicking the active one clears it.
    const next = { ...applied };
    if (next.role === role) delete next.role;
    else next.role = role;
    refetch(next);
  }

  function toggleCart() {
    window.clearTimeout(timer.current);
    refetch({ ...applied, has_cart: !applied.has_cart });
  }

  if (!data) return <Shell title="Users" sub="Loading…">{null}</Shell>;
  if (data.error)
    return (
      <Shell title="Users" sub="">
        {isAuthRequired(data)
          ? <AdminGate app={app} onSignedIn={() => refetch(applied)} />
          : <ErrorPanel error={data.error} />}
      </Shell>
    );

  const users = data.users ?? [];
  const spent = users.reduce((n, u) => n + u.spent_jpy, 0);
  const orders = users.reduce((n, u) => n + u.orders, 0);
  const none = Object.keys(applied).length === 0;
  const nf = (id: Field) => (applied[id] === undefined ? "" : String(applied[id]));
  const chip = (on: boolean) => ({
    variant: on ? ("light" as const) : ("default" as const),
    color: on ? "raksul" : "gray",
  });

  const bar = (
    <>
      <Group gap={6} mb={6}>
        <Button size="compact-xs" {...chip(none)} title="Clear every filter"
          onClick={() => pickRole("")}>All</Button>
        <Button size="compact-xs" tt="none" {...chip(applied.role === "admin")}
          onClick={() => pickRole("admin")}>admins</Button>
        <Button size="compact-xs" tt="none" {...chip(applied.role === "customer")}
          onClick={() => pickRole("customer")}>customers</Button>
        <Button size="compact-xs" tt="none" {...chip(Boolean(applied.has_cart))}
          title="Accounts with something left in the basket" onClick={toggleCart}>has cart</Button>
        <TextInput size="xs" w={190} placeholder="Name or email…" value={nf("q")}
          onChange={(e) => setField("q", e.currentTarget.value)} />
      </Group>
      <Group gap={6}>
        <Text size="xs" c="dimmed">orders</Text>
        <TextInput size="xs" w={92} type="number" placeholder="min" value={nf("min_orders")}
          onChange={(e) => setField("min_orders", e.currentTarget.value)} />
        <TextInput size="xs" w={92} type="number" placeholder="max" value={nf("max_orders")}
          onChange={(e) => setField("max_orders", e.currentTarget.value)} />
        <Text size="xs" c="dimmed">spent ¥</Text>
        <TextInput size="xs" w={92} type="number" placeholder="min" value={nf("min_spent")}
          onChange={(e) => setField("min_spent", e.currentTarget.value)} />
        <TextInput size="xs" w={92} type="number" placeholder="max" value={nf("max_spent")}
          onChange={(e) => setField("max_spent", e.currentTarget.value)} />
        <Text size="xs" c="dimmed">joined</Text>
        <TextInput size="xs" type="date" value={nf("from")}
          onChange={(e) => setField("from", e.currentTarget.value)} />
        <TextInput size="xs" type="date" value={nf("to")}
          onChange={(e) => setField("to", e.currentTarget.value)} />
      </Group>
    </>
  );

  return (
    <Shell
      title="Users"
      sub={loading ? "Loading…" : `${users.length} of ${data.total ?? users.length} accounts · ${orders} orders · ${yen(spent)}`}
      bar={bar}
    >
      {users.length === 0 ? (
        <Text size="sm" c="dimmed">Nothing to show.</Text>
      ) : (
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>ID</Table.Th><Table.Th>Name</Table.Th><Table.Th>Email</Table.Th>
              <Table.Th ta="right">Cart</Table.Th><Table.Th ta="right">Orders</Table.Th>
              <Table.Th ta="right">Spent</Table.Th><Table.Th>Joined</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {users.map((u) => (
              <Table.Tr key={u.id}>
                <Table.Td c="dimmed" ff="monospace" fz="xs">{u.id}</Table.Td>
                <Table.Td>
                  {u.name}
                  {u.is_admin && <Badge ml={6} size="xs" variant="light" color="gray" tt="none">admin</Badge>}
                </Table.Td>
                <Table.Td c="dimmed">{u.email}</Table.Td>
                <Table.Td ta="right">{u.cart_lines}</Table.Td>
                <Table.Td ta="right">{u.orders}</Table.Td>
                <Table.Td ta="right">{yen(u.spent_jpy)}</Table.Td>
                <Table.Td c="dimmed">{asDate(u.created_at)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Shell>
  );
}
