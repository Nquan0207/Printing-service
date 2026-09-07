import { useEffect, useState } from "react";
import {
  Badge,
  Button,
  Group,
  Paper,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { api, yen, type Order } from "../lib/api";

const STATUS_COLOR: Record<string, string> = {
  confirmed: "teal",
  pending: "yellow",
  cancelled: "red",
};

export default function Orders() {
  const [number, setNumber] = useState("");
  const [order, setOrder] = useState<Order | null>(null);

  useEffect(() => {
    const last = localStorage.getItem("stockroom.lastOrder");
    if (last) setNumber(last);
  }, []);

  async function lookup() {
    setOrder(null);
    try {
      const o = await api.order(number.trim());
      setOrder(o);
      localStorage.setItem("stockroom.lastOrder", o.order_number);
    } catch (e) {
      notifications.show({ color: "red", message: e instanceof Error ? e.message : "Lookup failed" });
    }
  }

  return (
    <Stack gap="md" maw={860}>
      <Title order={3}>Find an order</Title>
      <Group gap="sm">
        <TextInput
          placeholder="RKS-20260904-0001"
          value={number}
          onChange={(e) => setNumber(e.currentTarget.value)}
          onKeyDown={(e) => e.key === "Enter" && lookup()}
          w={280}
        />
        <Button onClick={lookup} disabled={!number.trim()}>
          Look up
        </Button>
      </Group>

      {order && (
        <Paper p="lg" radius="md">
          <Group justify="space-between" mb={4}>
            <Title order={4} ff="monospace">
              {order.order_number}
            </Title>
            <Badge color={STATUS_COLOR[order.status] ?? "gray"} variant="light">
              {order.status}
            </Badge>
          </Group>
          <Text size="sm" c="dimmed" mb="md">
            {new Date(order.created_at).toLocaleString()} · {order.shipping_address}
          </Text>

          <Table striped withRowBorders={false} verticalSpacing="xs">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Product</Table.Th>
                <Table.Th>Size</Table.Th>
                <Table.Th ta="right">Qty</Table.Th>
                <Table.Th ta="right">Unit</Table.Th>
                <Table.Th ta="right">Subtotal</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {order.items.map((i, n) => (
                <Table.Tr key={n}>
                  <Table.Td>{i.product_name}</Table.Td>
                  <Table.Td>{i.size_name}</Table.Td>
                  <Table.Td ta="right">{i.quantity}</Table.Td>
                  <Table.Td ta="right">{yen(i.unit_price_jpy)}</Table.Td>
                  <Table.Td ta="right">{yen(i.subtotal_jpy)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>

          <Group justify="space-between" mt="md" pt="sm" style={{ borderTop: "1px solid var(--mantine-color-default-border)" }}>
            <Text c="dimmed">Total</Text>
            <Text fw={700} fz="lg">
              {yen(order.total_jpy)}
            </Text>
          </Group>
        </Paper>
      )}
    </Stack>
  );
}
