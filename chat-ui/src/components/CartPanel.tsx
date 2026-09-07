import { useState } from "react";
import {
  ActionIcon,
  Button,
  Divider,
  Group,
  Paper,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { type Cart, yen } from "../lib/api";

type Props = {
  cart: Cart | null;
  onRemove: (itemId: number) => Promise<void>;
  onPrepare: (address: string) => Promise<void>;
};

export function CartPanel({ cart, onRemove, onPrepare }: Props) {
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState(false);
  const items = cart?.items ?? [];

  async function prepare(event: React.FormEvent) {
    event.preventDefault();
    if (!address.trim()) return;
    setBusy(true);
    try {
      await onPrepare(address.trim());
    } finally {
      setBusy(false);
    }
  }

  return (
    <Paper p="md" radius="lg">
      <Title order={3} size="h4">
        Cart · {cart?.item_count ?? 0}
      </Title>

      {!items.length && (
        <Text c="dimmed" size="sm" mt="xs">
          Your local database cart is empty.
        </Text>
      )}

      <Stack gap="xs" mt="sm">
        {items.map((item) => (
          <div key={item.id}>
            <Text fw={600} size="sm">
              {item.product_name}
            </Text>
            <Text size="xs" c="dimmed">
              {item.size_name} · quantity {item.quantity}
            </Text>
            <Group justify="space-between" mt={4}>
              <Text size="sm">{yen(item.subtotal_jpy)}</Text>
              <ActionIcon
                variant="subtle"
                color="red"
                aria-label={`Remove ${item.product_name}`}
                onClick={() => onRemove(item.id)}
              >
                ✕
              </ActionIcon>
            </Group>
            <Divider mt="xs" />
          </div>
        ))}
      </Stack>

      <Group justify="space-between" mt="sm">
        <Text fw={800}>Total</Text>
        <Text fw={800}>{yen(cart?.total_jpy ?? 0)}</Text>
      </Group>

      <form onSubmit={prepare}>
        <Stack gap="xs" mt="md">
          <TextInput
            placeholder="Mock shipping address"
            maxLength={500}
            required
            value={address}
            onChange={(event) => setAddress(event.currentTarget.value)}
          />
          <Button type="submit" loading={busy} disabled={!items.length}>
            Review mock order
          </Button>
        </Stack>
      </form>
    </Paper>
  );
}
