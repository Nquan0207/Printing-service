import { useCallback, useEffect, useState } from "react";
import {
  Badge,
  Button,
  Center,
  Group,
  Loader,
  NumberInput,
  Paper,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  TextInput,
} from "@mantine/core";
import { AreaChart, BarChart } from "@mantine/charts";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { api, yen, type AdminOrder, type AdminUser, type Product, type Stats } from "../lib/api";

export default function Admin() {
  return (
    <Tabs defaultValue="overview" keepMounted={false}>
      <Tabs.List mb="lg">
        <Tabs.Tab value="overview">Overview</Tabs.Tab>
        <Tabs.Tab value="orders">Orders</Tabs.Tab>
        <Tabs.Tab value="catalog">Catalog</Tabs.Tab>
        <Tabs.Tab value="users">Users</Tabs.Tab>
      </Tabs.List>
      <Tabs.Panel value="overview">
        <Overview />
      </Tabs.Panel>
      <Tabs.Panel value="orders">
        <OrdersTab />
      </Tabs.Panel>
      <Tabs.Panel value="catalog">
        <CatalogTab />
      </Tabs.Panel>
      <Tabs.Panel value="users">
        <UsersTab />
      </Tabs.Panel>
    </Tabs>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Paper p="md" radius="md">
      <Text size="xs" tt="uppercase" c="dimmed" fw={600} mb="md" style={{ letterSpacing: ".04em" }}>
        {title}
      </Text>
      {children}
    </Paper>
  );
}

function Tile({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <Paper p="md" radius="md">
      <Text size="xs" tt="uppercase" c="dimmed" fw={600} style={{ letterSpacing: ".04em" }}>
        {label}
      </Text>
      <Text fz={26} fw={700} mt={2} lh={1.2}>
        {value}
      </Text>
      {hint && (
        <Text size="xs" c="dimmed" mt={2}>
          {hint}
        </Text>
      )}
    </Paper>
  );
}

function Overview() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [days, setDays] = useState("14");

  useEffect(() => {
    api.admin
      .stats(Number(days))
      .then(setStats)
      .catch((e) => notifications.show({ color: "red", message: e.message }));
  }, [days]);

  if (!stats) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    );
  }
  const t = stats.totals;

  // Short labels keep the x-axis readable; the tooltip carries the full date.
  const series = stats.orders_by_day.map((d) => ({ ...d, label: d.date.slice(5) }));

  return (
    <Stack gap="md">
      <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }} spacing="md">
        <Tile label="Revenue" value={yen(t.revenue_jpy)} hint="cancelled excluded" />
        <Tile label="Orders" value={t.orders} hint={`${t.cancelled_orders} cancelled`} />
        <Tile label="Products" value={t.products} hint={`${t.active_products} active`} />
        <Tile label="Users" value={t.users} hint={`${t.open_cart_lines} open cart lines`} />
        <Tile label="Categories" value={t.categories} />
        <Tile label="Sizes" value={t.sizes} hint={`${t.images} images`} />
      </SimpleGrid>

      <Group gap="xs">
        <Text size="sm" c="dimmed">
          Range
        </Text>
        <SegmentedControl
          size="xs"
          value={days}
          onChange={setDays}
          data={["7", "14", "30", "90"].map((d) => ({ value: d, label: `${d}d` }))}
        />
      </Group>

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
        <Panel title="Revenue per day">
          <AreaChart
            h={220}
            data={series}
            dataKey="label"
            series={[{ name: "revenue_jpy", label: "Revenue", color: "raksul.6" }]}
            valueFormatter={(v) => yen(v)}
            curveType="monotone"
            withDots={false}
            gridAxis="y"
          />
        </Panel>
        <Panel title="Orders per day">
          <BarChart
            h={220}
            data={series}
            dataKey="label"
            series={[{ name: "orders", label: "Orders", color: "teal.6" }]}
            gridAxis="y"
          />
        </Panel>
        <Panel title="Products per category">
          <BarChart
            h={Math.max(220, stats.products_by_category.length * 32)}
            data={stats.products_by_category}
            dataKey="name"
            orientation="vertical"
            yAxisProps={{ width: 160, tick: { fontSize: 10 } }}
            series={[{ name: "count", label: "Products", color: "indigo.5" }]}
            gridAxis="x"
          />
        </Panel>
        <Panel title="Unit price distribution">
          <BarChart
            h={220}
            data={stats.price_buckets}
            dataKey="label"
            series={[{ name: "count", label: "Sizes", color: "orange.6" }]}
            gridAxis="y"
          />
        </Panel>
      </SimpleGrid>

      <Panel title="Top products by revenue">
        {stats.top_products.length === 0 ? (
          <Text c="dimmed">No orders yet.</Text>
        ) : (
          <Table striped withRowBorders={false} verticalSpacing="xs">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Product</Table.Th>
                <Table.Th ta="right">Units</Table.Th>
                <Table.Th ta="right">Revenue</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {stats.top_products.map((p, i) => (
                <Table.Tr key={i}>
                  <Table.Td>{p.product_name}</Table.Td>
                  <Table.Td ta="right">{p.quantity}</Table.Td>
                  <Table.Td ta="right">{yen(p.revenue_jpy)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Panel>
    </Stack>
  );
}

function OrdersTab() {
  const [orders, setOrders] = useState<AdminOrder[]>([]);
  const [status, setStatus] = useState("all");

  const load = useCallback(() => {
    api.admin
      .orders(status === "all" ? undefined : status)
      .then((r) => setOrders(r.orders))
      .catch((e) => notifications.show({ color: "red", message: e.message }));
  }, [status]);

  useEffect(load, [load]);

  async function change(orderNumber: string, next: string) {
    try {
      await api.admin.updateOrder(orderNumber, next);
      notifications.show({ color: "teal", message: `${orderNumber} → ${next}` });
      load();
    } catch (e) {
      notifications.show({ color: "red", message: e instanceof Error ? e.message : "Failed" });
    }
  }

  return (
    <Panel title={`Orders (${orders.length})`}>
      <SegmentedControl
        size="xs"
        mb="md"
        value={status}
        onChange={setStatus}
        data={["all", "confirmed", "pending", "cancelled"]}
      />
      <Table.ScrollContainer minWidth={720}>
        <Table striped highlightOnHover verticalSpacing="xs">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Order</Table.Th>
              <Table.Th>Customer</Table.Th>
              <Table.Th ta="right">Items</Table.Th>
              <Table.Th ta="right">Total</Table.Th>
              <Table.Th>Placed</Table.Th>
              <Table.Th>Status</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {orders.map((o) => (
              <Table.Tr key={o.order_number}>
                <Table.Td ff="monospace" fz="xs">
                  {o.order_number}
                </Table.Td>
                <Table.Td>
                  <Text size="sm">{o.user_name}</Text>
                  <Text size="xs" c="dimmed">
                    {o.user_email}
                  </Text>
                </Table.Td>
                <Table.Td ta="right">
                  <Badge
                    variant="light"
                    color="gray"
                    title={o.items
                      .map((i) => `${i.product_name} ${i.size_name} ×${i.quantity}`)
                      .join("\n")}
                  >
                    {o.items.length}
                  </Badge>
                </Table.Td>
                <Table.Td ta="right">{yen(o.total_jpy)}</Table.Td>
                <Table.Td c="dimmed" fz="xs">
                  {new Date(o.created_at).toLocaleDateString()}
                </Table.Td>
                <Table.Td>
                  <Select
                    size="xs"
                    w={130}
                    value={o.status}
                    onChange={(v) => v && change(o.order_number, v)}
                    data={["pending", "confirmed", "cancelled"]}
                    allowDeselect={false}
                  />
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {orders.length === 0 && (
        <Text c="dimmed" py="md">
          No orders.
        </Text>
      )}
    </Panel>
  );
}

function CatalogTab() {
  const [groups, setGroups] = useState<{ category: { id: number; name: string }; count: number; products: Product[] }[]>([]);
  const [q, setQ] = useState("");
  const [debounced] = useDebouncedValue(q, 250);
  const [editing, setEditing] = useState<number | null>(null);

  const load = useCallback(() => {
    api.admin
      .products(debounced || undefined)
      .then((r) => setGroups(r.groups))
      .catch((e) => notifications.show({ color: "red", message: e.message }));
  }, [debounced]);

  useEffect(load, [load]);

  return (
    <Panel title={`Catalog (${groups.reduce((n, g) => n + g.count, 0)})`}>
      <TextInput
        placeholder="Filter products…"
        value={q}
        onChange={(e) => setQ(e.currentTarget.value)}
        mb="md"
        maw={320}
      />
      {groups.map((g) => (
        <Table.ScrollContainer minWidth={820} key={g.category.id} mb="md">
          <Group gap="xs" mb={4}>
            <Text fw={600} size="sm">
              {g.category.name}
            </Text>
            <Badge size="sm" variant="light" color="gray">
              {g.count}
            </Badge>
          </Group>
          <Table striped highlightOnHover verticalSpacing="xs">
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={60}>ID</Table.Th>
                <Table.Th>Name</Table.Th>
                <Table.Th ta="right">Base</Table.Th>
                <Table.Th>Sizes</Table.Th>
                <Table.Th w={200} />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {g.products.map((p) =>
                editing === p.id ? (
                  <ProductEditor
                    key={p.id}
                    product={p}
                    onDone={() => {
                      setEditing(null);
                      load();
                    }}
                  />
                ) : (
                  <Table.Tr key={p.id}>
                    <Table.Td c="dimmed" fz="xs">
                      {p.id}
                    </Table.Td>
                    <Table.Td>{p.name}</Table.Td>
                    <Table.Td ta="right">{yen(p.base_price_jpy)}</Table.Td>
                    <Table.Td c="dimmed" fz="xs">
                      {p.sizes.map((s) => `${s.size_name} ${yen(s.unit_price_jpy)}`).join(" · ")}
                    </Table.Td>
                    <Table.Td>
                      <Button size="compact-xs" variant="default" onClick={() => setEditing(p.id)}>
                        Edit
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ),
              )}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      ))}
      {groups.length === 0 && <Text c="dimmed">No products.</Text>}
      <Text size="xs" c="dimmed" mt="sm">
        Edits are overwritten by the next crawl, which upserts on{" "}
        <Text span ff="monospace" fz="xs">
          source_product_id
        </Text>
        . Deactivation survives.
      </Text>
    </Panel>
  );
}

function ProductEditor({ product, onDone }: { product: Product; onDone: () => void }) {
  const [name, setName] = useState(product.name);
  const [price, setPrice] = useState<string | number>(product.base_price_jpy);
  // Size adjustments are edited alongside the base price: on their own the
  // numbers are meaningless, since unit price = base + adjustment.
  const [adjustments, setAdjustments] = useState<Record<number, string | number>>(
    Object.fromEntries(product.sizes.map((s) => [s.id, s.price_adjustment_jpy])),
  );
  const [busy, setBusy] = useState(false);

  const base = Number(price) || 0;

  async function saveAll() {
    setBusy(true);
    try {
      await api.admin.updateProduct(product.id, {
        name: name.trim(),
        base_price_jpy: base,
      });
      // Only send sizes whose adjustment actually changed.
      const changed = product.sizes.filter(
        (s) => Number(adjustments[s.id]) !== s.price_adjustment_jpy,
      );
      for (const s of changed) {
        await api.admin.updateSize(s.id, { price_adjustment_jpy: Number(adjustments[s.id]) });
      }
      notifications.show({
        color: "teal",
        message: `Product ${product.id} updated${changed.length ? ` · ${changed.length} size(s)` : ""}`,
      });
      onDone();
    } catch (e) {
      notifications.show({ color: "red", message: e instanceof Error ? e.message : "Failed" });
      setBusy(false);
    }
  }

  async function deactivate() {
    setBusy(true);
    try {
      await api.admin.updateProduct(product.id, { is_active: false });
      notifications.show({ color: "teal", message: `Product ${product.id} deactivated` });
      onDone();
    } catch (e) {
      notifications.show({ color: "red", message: e instanceof Error ? e.message : "Failed" });
      setBusy(false);
    }
  }

  return (
    <Table.Tr bg="var(--mantine-color-default-hover)">
      <Table.Td colSpan={6}>
        <Stack gap="sm" p="xs">
          <Group gap="sm" align="end" wrap="wrap">
            <TextInput
              label="Name"
              size="xs"
              value={name}
              onChange={(e) => setName(e.currentTarget.value)}
              style={{ flex: 1, minWidth: 260 }}
            />
            <NumberInput
              label="Base price"
              size="xs"
              w={130}
              min={0}
              value={price}
              onChange={setPrice}
              prefix="¥"
              thousandSeparator
            />
          </Group>

          <div>
            <Text size="xs" c="dimmed" fw={600} mb={6}>
              Size adjustments — unit price = base + adjustment
            </Text>
            <Group gap="sm" wrap="wrap">
              {product.sizes.map((s) => {
                const adj = Number(adjustments[s.id]) || 0;
                return (
                  <Group key={s.id} gap={6} align="end">
                    <NumberInput
                      label={`${s.size_name} adjustment`}
                      size="xs"
                      w={140}
                      value={adjustments[s.id]}
                      onChange={(v) => setAdjustments((a) => ({ ...a, [s.id]: v }))}
                      prefix="¥"
                      thousandSeparator
                      allowNegative
                    />
                    <Badge variant="light" color="gray" mb={4}>
                      = {yen(base + adj)}
                    </Badge>
                  </Group>
                );
              })}
            </Group>
          </div>

          <Group gap="xs">
            <Button size="compact-sm" loading={busy} onClick={saveAll}>
              Save
            </Button>
            <Button size="compact-sm" variant="light" color="red" disabled={busy} onClick={deactivate}>
              Deactivate
            </Button>
            <Button size="compact-sm" variant="subtle" color="gray" disabled={busy} onClick={onDone}>
              Cancel
            </Button>
          </Group>
        </Stack>
      </Table.Td>
    </Table.Tr>
  );
}

function UsersTab() {
  const [users, setUsers] = useState<AdminUser[]>([]);

  useEffect(() => {
    api.admin
      .users()
      .then((r) => setUsers(r.users))
      .catch((e) => notifications.show({ color: "red", message: e.message }));
  }, []);

  return (
    <Panel title={`Users (${users.length})`}>
      <Table.ScrollContainer minWidth={640}>
        <Table striped highlightOnHover verticalSpacing="xs">
          <Table.Thead>
            <Table.Tr>
              <Table.Th w={60}>ID</Table.Th>
              <Table.Th>Name</Table.Th>
              <Table.Th>Email</Table.Th>
              <Table.Th ta="right">Cart</Table.Th>
              <Table.Th ta="right">Orders</Table.Th>
              <Table.Th ta="right">Spent</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {users.map((u) => (
              <Table.Tr key={u.id}>
                <Table.Td c="dimmed" fz="xs">
                  {u.id}
                </Table.Td>
                <Table.Td>
                  <Group gap={6}>
                    {u.name}
                    {u.is_admin && (
                      <Badge size="xs" variant="light" color="raksul">
                        admin
                      </Badge>
                    )}
                  </Group>
                </Table.Td>
                <Table.Td c="dimmed" fz="xs">
                  {u.email}
                </Table.Td>
                <Table.Td ta="right">{u.cart_lines}</Table.Td>
                <Table.Td ta="right">{u.orders}</Table.Td>
                <Table.Td ta="right">{yen(u.spent_jpy)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Panel>
  );
}
