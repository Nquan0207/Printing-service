import { useEffect, useState } from "react";
import {
  Alert, Box, Button, Divider, Group, Stack, Table, Text, TextInput, Title,
} from "@mantine/core";
import { app, callTool, initialToolOutput, unwrap } from "../lib/mcp";
import { Identify } from "../components/Identify";
import { yen } from "../lib/format";

type CartItem = {
  id: number; product_name: string; size_name: string;
  quantity: number; subtotal_jpy: number;
};
type Cart = { items: CartItem[]; item_count: number; total_jpy: number };
type Confirmation = { token: string; shipping_address: string };
type Payload = {
  cart?: Cart;
  user?: { name: string; email: string } | null;
  confirmation?: Confirmation;
  order?: { order_number: string; total_jpy: number };
  status?: string;
  error?: { code: string; message: string };
};

export default function CartView() {
  const [cart, setCart] = useState<Cart | null>(null);
  const [user, setUser] = useState<Payload["user"]>(null);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [order, setOrder] = useState<Payload["order"] | null>(null);
  const [address, setAddress] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  /** Offered, never required: the cart works fine anonymously, and a shopper
   *  who wants it kept against their account can say so at any point rather
   *  than only at checkout. */
  const [identifying, setIdentifying] = useState(false);

  function seed(out: Payload | null) {
    if (!out) return;
    if (out.cart) setCart(out.cart);
    if (out.user !== undefined) setUser(out.user);
    if (out.confirmation) setConfirmation(out.confirmation);
    if (out.order) setOrder(out.order);
  }

  async function run(fn: () => Promise<Payload>) {
    setBusy(true);
    setMessage(null);
    try {
      seed(await fn());
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const refresh = () => run(() => callTool<Payload>("get_cart"));
  const remove = (id: number) => run(() => callTool<Payload>("remove_cart_item", { item_id: id }));

  const checkout = () =>
    run(async () => {
      const out = await callTool<Payload>("prepare_order", {
        shipping_address: address,
        // Only while still a guest; the server ignores them once the shopper
        // is known, so a returning buyer is never asked twice.
        ...(user ? {} : { name: name.trim(), email: email.trim() }),
      });
      setOrder(null);
      return out;
    });

  const decide = (decision: "approve" | "reject") =>
    run(async () => {
      if (!confirmation) return {};
      // The token is the capability that authorises the write; place_order
      // refuses without it, so no order can be placed by asking nicely.
      const out = await callTool<Payload>("place_order", {
        confirmation_token: confirmation.token,
        decision,
      });
      setConfirmation(null);
      if (decision === "reject") setMessage("Rejected. Your cart was kept.");
      return { ...out, cart: (await callTool<Payload>("get_cart")).cart };
    });

  useEffect(() => {
    const initial = initialToolOutput();
    if (initial) seed(initial);
    app.ontoolresult = (result: unknown) => seed(unwrap<Payload>(result));
    void app.connect();
    if (!initial) void refresh();
  }, []);

  if (!cart) return <Box p="md"><Text size="sm" c="dimmed">Loading…</Text></Box>;

  const empty = cart.items.length === 0;

  return (
    <Box p="md">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Title order={1} size="h4">Your cart</Title>
        <Button size="compact-xs" variant="subtle" loading={busy} onClick={refresh}>
          Refresh
        </Button>
      </Group>
      <Group gap="xs" align="center" mb="sm">
        <Text size="xs" c="dimmed">
          {cart.item_count} line{cart.item_count === 1 ? "" : "s"}
          {user ? ` · ${user.email}` : " · browsing as guest"}
        </Text>
        {!user && !identifying && (
          <Button size="compact-xs" variant="subtle" onClick={() => setIdentifying(true)}>
            Sign in
          </Button>
        )}
      </Group>

      {!user && identifying && (
        <Box mb="sm">
          <Identify
            title="Sign in"
            hint="Your cart follows you to the account, and checkout stops asking."
            onSignedIn={() => {
              setIdentifying(false);
              // Signing in claims the guest cart, so re-read it rather than
              // trusting the copy on screen.
              void refresh();
            }}
          />
        </Box>
      )}

      {empty ? (
        <Text size="sm" c="dimmed">Nothing in the cart yet.</Text>
      ) : (
        <>
          <Table fz="sm">
            <Table.Tbody>
              {cart.items.map((it) => (
                <Table.Tr key={it.id}>
                  <Table.Td>
                    {it.product_name}
                    <Text span size="xs" c="dimmed"> · {it.size_name}</Text>
                  </Table.Td>
                  <Table.Td ta="right" w={60}>×{it.quantity}</Table.Td>
                  <Table.Td ta="right" w={90}>{yen(it.subtotal_jpy)}</Table.Td>
                  <Table.Td ta="right" w={70}>
                    <Button size="compact-xs" variant="subtle" color="red"
                            disabled={busy} onClick={() => remove(it.id)}>
                      Remove
                    </Button>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>

          <Group justify="space-between" mt="xs">
            <Text fw={800}>Total</Text>
            <Text fw={800}>{yen(cart.total_jpy)}</Text>
          </Group>

          <Divider my="sm" />

          <Stack gap="xs">
            <TextInput size="xs" placeholder="Shipping address" value={address}
              onChange={(e) => setAddress(e.currentTarget.value)} />
            {!user && (
              <>
                <Text size="xs" c="dimmed">Who is this order for?</Text>
                <Group gap="xs" grow wrap="nowrap">
                  <TextInput size="xs" placeholder="Name" value={name}
                    onChange={(e) => setName(e.currentTarget.value)} />
                  <TextInput size="xs" placeholder="Email" type="email" value={email}
                    onChange={(e) => setEmail(e.currentTarget.value)} />
                </Group>
              </>
            )}
            <Button size="xs" loading={busy}
                    disabled={!address.trim() || (!user && !email.trim())}
                    onClick={checkout}>
              Review order
            </Button>
          </Stack>
        </>
      )}

      {confirmation && (
        <Alert color="raksul" variant="light" mt="sm" title="Confirm this mock order">
          <Text size="xs">Ships to {confirmation.shipping_address}</Text>
          <Group gap="xs" mt="xs">
            <Button size="xs" loading={busy} onClick={() => decide("approve")}>Approve</Button>
            <Button size="xs" variant="default" loading={busy} onClick={() => decide("reject")}>
              Reject
            </Button>
          </Group>
        </Alert>
      )}

      {order && (
        <Alert color="green" variant="light" mt="sm" title="Mock receipt">
          <Text size="xs">{order.order_number}</Text>
          <Text size="xs" fw={700}>Total {yen(order.total_jpy)}</Text>
        </Alert>
      )}

      {message && <Alert color="gray" variant="light" mt="sm">{message}</Alert>}
    </Box>
  );
}
