import { Button, Group, Paper, Stack, Text, Title } from "@mantine/core";
import { type Confirmation, type Order, yen } from "../lib/api";

type Props = {
  confirmation: Confirmation | null;
  decision: string | null;
  order: Order | null;
  onDecide: (decision: "approve" | "reject") => Promise<void>;
};

export function CheckoutPanel({ confirmation, decision, order, onDecide }: Props) {
  if (order) {
    return (
      <Paper p="md" radius="lg" bg="green.0" style={{ borderColor: "var(--mantine-color-green-3)" }}>
        <Stack gap={4}>
          <Title order={3} size="h4">
            Mock receipt
          </Title>
          <Text size="sm">{order.order_number}</Text>
          <Text fw={800}>Total {yen(order.total_jpy)}</Text>
          <Text size="xs" c="dimmed">
            No money moved.
          </Text>
        </Stack>
      </Paper>
    );
  }

  if (!confirmation) return null;

  return (
    <Paper p="md" radius="lg" bg="raksul.0" style={{ borderColor: "var(--mantine-color-raksul-3)" }}>
      <Stack gap={6}>
        <Title order={3} size="h4">
          Confirm mock order
        </Title>
        <Text size="sm">Ship to: {confirmation.shipping_address}</Text>
        <Text size="xs" c="dimmed">
          Expires: {new Date(confirmation.expires_at).toLocaleString()}
        </Text>

        {decision ? (
          <Text fw={700} mt="xs">
            Decision: {decision}
          </Text>
        ) : (
          // place_order is never given to the model: only these two buttons
          // can reach it, which is the confirm gate the requirement asks for.
          <Group grow mt="xs">
            <Button variant="light" color="red" onClick={() => onDecide("reject")}>
              Reject
            </Button>
            <Button color="green" onClick={() => onDecide("approve")}>
              Approve
            </Button>
          </Group>
        )}
      </Stack>
    </Paper>
  );
}
