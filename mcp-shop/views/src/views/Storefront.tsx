import { useEffect, useState } from "react";
import {
  Alert, Anchor, Badge, Button, Card, Center, Group, Image, NumberInput, Paper,
  SimpleGrid, Stack, Text, TextInput, Title,
} from "@mantine/core";
import { app, callTool, initialToolOutput, isOpenAIHost, unwrap } from "../lib/mcp";

type Size = { id: number; size_name: string; unit_price_jpy: number };
type Product = {
  id: number; name: string; brand: string | null;
  category: { name: string } | null;
  base_price_jpy: number; sizes: Size[]; images: string[];
};
type CartItem = { id: number; product_name: string; size_name: string; quantity: number; subtotal_jpy: number };
type Cart = { items: CartItem[]; item_count: number; total_jpy: number };
type User = { name: string; email: string };
type Confirmation = { shipping_address: string };
type Order = { order_number: string; total_jpy: number };

const yen = (v: unknown) => (Number.isInteger(v) ? `¥${(v as number).toLocaleString()}` : "—");

/**
 * Product text is crawled from a live site, so an image field is untrusted
 * input. Only https, loopback http and data:image survive.
 */
function safeImageUrl(value: unknown): string {
  if (typeof value !== "string") return "";
  const ok =
    /^https:\/\//i.test(value) ||
    /^http:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?\//i.test(value) ||
    /^data:image\//i.test(value);
  return ok ? value : "";
}

function ProductCard({ product, busy, onAdd }: {
  product: Product;
  busy: boolean;
  onAdd: (productId: number, sizeId: number, quantity: number) => void;
}) {
  const sizes = product.sizes ?? [];
  const [sizeId, setSizeId] = useState<string | null>(sizes[0] ? String(sizes[0].id) : null);
  const [quantity, setQuantity] = useState(1);
  const image = safeImageUrl(product.images?.[0]);

  return (
    <Card padding="sm">
      <Card.Section>
        {image ? (
          <Image src={image} alt="" h={130} fit="contain" bg="var(--mantine-color-default-hover)" />
        ) : (
          <Center h={130} bg="var(--mantine-color-default-hover)">
            <Text size="xs" c="dimmed">No image</Text>
          </Center>
        )}
      </Card.Section>
      <Stack gap={5} mt="xs">
        <Text fw={600} size="sm" lineClamp={2} title={product.name}>{product.name}</Text>
        <Text size="xs" c="dimmed">{product.category?.name || product.brand || ""}</Text>
        <Text fw={800}>From {yen(product.base_price_jpy)}</Text>
        <Group gap={6} grow wrap="nowrap">
          {/* A native select: Mantine's Select renders a portal-ed dropdown,
              which is awkward inside a short auto-resized iframe. */}
          <select
            aria-label="Size"
            value={sizeId ?? ""}
            onChange={(e) => setSizeId(e.currentTarget.value || null)}
            style={{
              font: "inherit", padding: "5px 7px", borderRadius: 7, minWidth: 0,
              border: "1px solid var(--mantine-color-default-border)",
              background: "var(--mantine-color-body)", color: "inherit",
            }}
          >
            {sizes.map((s) => (
              <option key={s.id} value={s.id}>{s.size_name} · {yen(s.unit_price_jpy)}</option>
            ))}
          </select>
          <NumberInput
            size="xs" aria-label="Quantity" min={1} max={100} clampBehavior="strict"
            value={quantity} maw={72}
            onChange={(v) => setQuantity(typeof v === "number" ? v : 1)}
          />
        </Group>
        <Button
          size="xs"
          disabled={busy || !sizes.length || !sizeId}
          onClick={() => sizeId && onAdd(product.id, Number(sizeId), quantity)}
        >
          Quote and add
        </Button>
      </Stack>
    </Card>
  );
}

export default function Storefront() {
  const [products, setProducts] = useState<Product[]>([]);
  const [user, setUser] = useState<User | null>(null);
  const [cart, setCart] = useState<Cart | null>(null);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [order, setOrder] = useState<Order | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; bad?: boolean } | null>(null);
  const [bridgeError, setBridgeError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [query, setQuery] = useState("");
  const [address, setAddress] = useState("");

  /** Apply whatever a tool result carried; every tool returns the same envelope. */
  function seed(out: any) {
    if (!out || typeof out !== "object") return;
    if (out.groups) setProducts(out.groups.flatMap((g: any) => g.products ?? []));
    if (out.user) setUser(out.user);
    if (out.cart) setCart(out.cart);
    if (out.confirmation) setConfirmation(out.confirmation);
    if (out.order) setOrder(out.order);
  }

  useEffect(() => {
    if (isOpenAIHost()) {
      seed(initialToolOutput());
      return;
    }
    // The host pushes the first result when it renders the View.
    app.ontoolresult = (result: unknown) => seed(unwrap(result));
    // A blank iframe reads as a host bug, so failures always render.
    app.connect().catch((error: any) => setBridgeError(error?.message || String(error)));
  }, []);

  async function run<T>(work: () => Promise<T>, done?: (out: T) => void) {
    setBusy(true);
    try {
      done?.(await work());
    } catch (error: any) {
      setMessage({ text: error?.message ?? String(error), bad: true });
    } finally {
      setBusy(false);
    }
  }

  const signIn = () =>
    run(async () => {
      const signedIn = await callTool("mock_sign_in", { name, email });
      const withCart = await callTool("get_cart");
      return { ...signedIn, cart: withCart.cart };
    }, (out) => {
      seed(out);
      setMessage({ text: "Database user and cart loaded." });
    });

  const search = () =>
    run(() => callTool("search_products", { query: query || null, limit: 30 }), (out) => {
      seed(out);
      setMessage({ text: `${out.count ?? 0} product(s).` });
    });

  const add = (productId: number, sizeId: number, quantity: number) =>
    run(() => callTool("add_to_cart", { product_id: productId, size_id: sizeId, quantity }), (out) => {
      seed(out);
      setConfirmation(null);
      setOrder(null);
      setMessage({ text: "Added to the database cart." });
    });

  const removeLine = (itemId: number) =>
    run(() => callTool("remove_cart_item", { item_id: itemId }), (out) => {
      seed(out);
      setConfirmation(null);
    });

  const prepare = () =>
    run(() => callTool("prepare_order", { shipping_address: address }), (out) => {
      seed(out);
      setOrder(null);
      setMessage({ text: "Review the confirmation before approving." });
    });

  const decide = (decision: "approve" | "reject") =>
    run(() => callTool("place_order", { decision }), (out) => {
      setConfirmation(null);
      if (decision === "approve") {
        setOrder(out.order);
        setCart({ items: [], item_count: 0, total_jpy: 0 });
        setMessage({ text: "Mock order stored in the Stockroom database." });
      } else {
        setMessage({ text: "Rejected. Database cart preserved." });
      }
    });

  return (
    <Stack gap="sm" p="md">
      <Group justify="space-between" align="center">
        <Title order={1} size="h4">RAKSUL Stockroom</Title>
        <Badge color="raksul" variant="light">DATABASE MOCK</Badge>
      </Group>

      <Text size="xs" c="dimmed">
        Catalog, sizes, cart and orders come from the Stockroom backend through MCP tools.
        No supplier website opens and no real payment occurs.
      </Text>

      {bridgeError && (
        <Alert color="red" variant="light" title="MCP App bridge error">{bridgeError}</Alert>
      )}

      {!user ? (
        <Paper p="md" radius="md">
          <Stack gap="xs">
            <Title order={2} size="h5">Select demo user</Title>
            <Text size="xs" c="dimmed">
              This creates or selects a database user without a password.
            </Text>
            <Group gap="xs" grow align="flex-end" wrap="nowrap">
              <TextInput size="xs" label="Name" value={name}
                onChange={(e) => setName(e.currentTarget.value)} />
              <TextInput size="xs" label="Email" type="email" required value={email}
                onChange={(e) => setEmail(e.currentTarget.value)} />
              <Button size="xs" maw={110} loading={busy} onClick={signIn}>Continue</Button>
            </Group>
          </Stack>
        </Paper>
      ) : (
        <>
          <Text size="xs" c="dimmed">
            Demo user <b>{user.name}</b> · {user.email}
          </Text>

          <Group gap="xs" wrap="nowrap">
            <TextInput size="xs" flex={1} placeholder="Search Stockroom products"
              value={query} onChange={(e) => setQuery(e.currentTarget.value)}
              onKeyDown={(e) => e.key === "Enter" && search()} />
            <Button size="xs" loading={busy} onClick={search}>Search</Button>
          </Group>

          {message && (
            <Text size="xs" c={message.bad ? "red" : "dimmed"}>{message.text}</Text>
          )}

          <Group align="flex-start" gap="md" wrap="wrap">
            <div style={{ flex: "1 1 380px", minWidth: 0 }}>
              {products.length ? (
                <SimpleGrid cols={{ base: 1, xs: 2, md: 3 }} spacing="xs">
                  {products.map((p) => (
                    <ProductCard key={p.id} product={p} busy={busy} onAdd={add} />
                  ))}
                </SimpleGrid>
              ) : (
                <Text size="xs" c="dimmed">No products in the Stockroom database.</Text>
              )}
            </div>

            <Paper p="md" radius="md" style={{ flex: "0 1 320px", minWidth: 260 }}>
              <Title order={2} size="h5">Cart · {cart?.item_count ?? 0}</Title>
              {!cart ? (
                <Text size="xs" c="dimmed" mt="xs">Loading database cart…</Text>
              ) : (
                <Stack gap="xs" mt="xs">
                  {cart.items.length === 0 && <Text size="xs" c="dimmed">Empty cart.</Text>}
                  {cart.items.map((item) => (
                    <div key={item.id}>
                      <Text size="sm" fw={600}>{item.product_name}</Text>
                      <Text size="xs" c="dimmed">{item.size_name} · {item.quantity}</Text>
                      <Group justify="space-between">
                        <Text size="sm">{yen(item.subtotal_jpy)}</Text>
                        <Anchor component="button" type="button" size="xs" c="red"
                          onClick={() => removeLine(item.id)}>Remove</Anchor>
                      </Group>
                    </div>
                  ))}
                  <Group justify="space-between">
                    <Text fw={800}>Total</Text>
                    <Text fw={800}>{yen(cart.total_jpy)}</Text>
                  </Group>
                  <TextInput size="xs" placeholder="Mock shipping address" value={address}
                    onChange={(e) => setAddress(e.currentTarget.value)} />
                  <Button size="xs" disabled={busy || !cart.items.length} onClick={prepare}>
                    Review mock order
                  </Button>
                </Stack>
              )}

              {confirmation && (
                <Alert color="raksul" variant="light" mt="sm" title="Explicit mock confirmation">
                  <Text size="xs">Address: {confirmation.shipping_address}</Text>
                  <Text size="xs">Total: {yen(cart?.total_jpy)}</Text>
                  {/* place_order is withheld from the model; only these reach it. */}
                  <Stack gap={6} mt="xs">
                    <Button size="xs" color="green" onClick={() => decide("approve")}>
                      Approve mock order
                    </Button>
                    <Button size="xs" variant="light" color="red" onClick={() => decide("reject")}>
                      Reject mock order
                    </Button>
                  </Stack>
                </Alert>
              )}

              {order && (
                <Alert color="green" variant="light" mt="sm" title="Mock receipt">
                  <Text size="xs">{order.order_number}</Text>
                  <Text size="xs" fw={700}>Total {yen(order.total_jpy)}</Text>
                  <Text size="xs" c="dimmed">No money moved.</Text>
                </Alert>
              )}
            </Paper>
          </Group>
        </>
      )}
    </Stack>
  );
}
