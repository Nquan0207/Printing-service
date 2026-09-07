import { useEffect, useMemo, useState } from "react";
import {
  Alert, Anchor, Badge, Button, Card, Center, Group, Image, NumberInput, Pagination,
  Paper, SimpleGrid, Stack, Text, TextInput, Title,
} from "@mantine/core";
import { app, callTool, initialToolOutput, isOpenAIHost, unwrap } from "../lib/mcp";

type Size = { id: number; size_name: string; unit_price_jpy: number };
type Product = {
  id: number; name: string; brand: string | null;
  category: { name: string } | null;
  base_price_jpy: number; sizes: Size[]; images: string[];
};
type Category = { id: number; slug: string; name: string; product_count: number };
type Group = { category: { slug: string; name: string }; count: number; products: Product[] };
type CartItem = { id: number; product_name: string; size_name: string; quantity: number; subtotal_jpy: number };
type Cart = { items: CartItem[]; item_count: number; total_jpy: number };
type User = { name: string; email: string };
type Confirmation = { shipping_address: string };
type Order = { order_number: string; total_jpy: number };

/** Products per page inside a category. */
const PAGE_SIZE = 12;
/** The Go API caps a request at 100 products; the largest category holds 34,
 *  so one call always fetches a whole category and paging stays client-side. */
const CATEGORY_FETCH_LIMIT = 100;
/** Pseudo-slug for "these are search results, not a category". */
const SEARCH = "__search__";

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
  const [categories, setCategories] = useState<Category[]>([]);
  /** Slug of the category on screen, or SEARCH. */
  const [active, setActive] = useState<string | null>(null);
  /** Whole categories, fetched once each and kept. Nothing here is re-fetched
   *  when you page or switch back, so browsing costs one call per category. */
  const [cache, setCache] = useState<Record<string, Product[]>>({});
  const [page, setPage] = useState(1);

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

  /** Apply the commerce parts of any tool result; every tool shares the envelope. */
  function seedCommerce(out: any) {
    if (!out || typeof out !== "object") return;
    if (out.user) setUser(out.user);
    if (out.cart) setCart(out.cart);
    if (out.confirmation) setConfirmation(out.confirmation);
    if (out.order) setOrder(out.order);
  }

  /** Load the category list, then open whichever category the model asked for. */
  async function bootstrap(seed: any) {
    seedCommerce(seed);
    try {
      const list = await callTool<{ categories?: Category[] }>("list_categories");
      const cats = list.categories ?? [];
      setCategories(cats);

      // If the prompt named a category, the seed's groups say which.
      const groups: Group[] = seed?.groups ?? [];
      const first = groups[0]?.category?.slug ?? cats[0]?.slug ?? null;
      if (first) void openCategory(first, cats);
    } catch (error: any) {
      setMessage({ text: error?.message ?? String(error), bad: true });
    }
  }

  useEffect(() => {
    if (isOpenAIHost()) {
      void bootstrap(initialToolOutput());
      return;
    }
    app.ontoolresult = (result: unknown) => void bootstrap(unwrap(result));
    app.connect().catch((error: any) => setBridgeError(error?.message || String(error)));
  }, []);

  /** Fetch one whole category, once, and show its first page. */
  async function openCategory(slug: string, known = categories) {
    setActive(slug);
    setPage(1);
    setQuery("");
    if (cache[slug]) return;

    setBusy(true);
    try {
      const out = await callTool<{ groups?: Group[] }>("search_products", {
        category: slug,
        limit: CATEGORY_FETCH_LIMIT,
      });
      const products = (out.groups ?? []).flatMap((g) => g.products ?? []);
      setCache((c) => ({ ...c, [slug]: products }));
      const label = known.find((c) => c.slug === slug)?.name ?? slug;
      setMessage({ text: `${label} — ${products.length} product(s).` });
    } catch (error: any) {
      setMessage({ text: error?.message ?? String(error), bad: true });
    } finally {
      setBusy(false);
    }
  }

  async function runSearch() {
    const q = query.trim();
    if (!q) return;
    setBusy(true);
    try {
      const out = await callTool<{ groups?: Group[]; count?: number }>("search_products", {
        query: q,
        limit: CATEGORY_FETCH_LIMIT,
      });
      const products = (out.groups ?? []).flatMap((g) => g.products ?? []);
      setCache((c) => ({ ...c, [SEARCH]: products }));
      setActive(SEARCH);
      setPage(1);
      setMessage({ text: `${products.length} product(s) matching “${q}”.` });
    } catch (error: any) {
      setMessage({ text: error?.message ?? String(error), bad: true });
    } finally {
      setBusy(false);
    }
  }

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
      seedCommerce(out);
      setMessage({ text: "Database user and cart loaded." });
    });

  const add = (productId: number, sizeId: number, quantity: number) =>
    run(() => callTool("add_to_cart", { product_id: productId, size_id: sizeId, quantity }), (out) => {
      seedCommerce(out);
      setConfirmation(null);
      setOrder(null);
      setMessage({ text: "Added to the database cart." });
    });

  const removeLine = (itemId: number) =>
    run(() => callTool("remove_cart_item", { item_id: itemId }), (out) => {
      seedCommerce(out);
      setConfirmation(null);
    });

  const prepare = () =>
    run(() => callTool("prepare_order", { shipping_address: address }), (out) => {
      seedCommerce(out);
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

  const shown = active ? cache[active] ?? [] : [];
  const pageCount = Math.max(1, Math.ceil(shown.length / PAGE_SIZE));
  const pageItems = useMemo(
    () => shown.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [shown, page],
  );
  const activeName =
    active === SEARCH
      ? `Search: ${query || "results"}`
      : categories.find((c) => c.slug === active)?.name ?? "";

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

          {/* Every category, always. Clicking one loads it whole and pages
              through it here rather than asking the model for more. */}
          <Group gap={6}>
            {categories.map((c) => (
              <Button
                key={c.slug}
                size="compact-xs"
                tt="none"
                title={c.slug}
                disabled={busy}
                variant={active === c.slug ? "light" : "default"}
                color={active === c.slug ? "raksul" : "gray"}
                onClick={() => openCategory(c.slug)}
              >
                {c.name}
                <Text span c="dimmed" ml={5}>{c.product_count}</Text>
              </Button>
            ))}
          </Group>

          <Group gap="xs" wrap="nowrap">
            <TextInput size="xs" flex={1} placeholder="Search across every category…"
              value={query} onChange={(e) => setQuery(e.currentTarget.value)}
              onKeyDown={(e) => e.key === "Enter" && runSearch()} />
            <Button size="xs" loading={busy} onClick={runSearch}>Search</Button>
          </Group>

          {message && (
            <Text size="xs" c={message.bad ? "red" : "dimmed"}>{message.text}</Text>
          )}

          <Group align="flex-start" gap="md" wrap="wrap">
            <Stack gap="xs" style={{ flex: "1 1 380px", minWidth: 0 }}>
              <Group justify="space-between" align="center">
                <Title order={2} size="h5">{activeName}</Title>
                {shown.length > 0 && (
                  <Text size="xs" c="dimmed">
                    {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, shown.length)} of {shown.length}
                  </Text>
                )}
              </Group>

              {shown.length === 0 ? (
                <Text size="xs" c="dimmed">
                  {busy ? "Loading…" : "No products here."}
                </Text>
              ) : (
                <>
                  <SimpleGrid cols={{ base: 1, xs: 2, md: 3 }} spacing="xs">
                    {pageItems.map((p) => (
                      <ProductCard key={p.id} product={p} busy={busy} onAdd={add} />
                    ))}
                  </SimpleGrid>
                  {pageCount > 1 && (
                    <Group justify="center" mt="xs">
                      {/* Paging is local: the whole category is already here. */}
                      <Pagination size="sm" total={pageCount} value={page} onChange={setPage} withEdges />
                    </Group>
                  )}
                </>
              )}
            </Stack>

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
