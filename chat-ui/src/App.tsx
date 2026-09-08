import { useCallback, useEffect, useRef, useState } from "react";
import {
  Badge,
  Button,
  Container,
  Grid,
  Group,
  Loader,
  Paper,
  Stack,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";

import type { AppDescriptor } from "./components/MCPApp";
import { CartPanel } from "./components/CartPanel";
import { CheckoutPanel } from "./components/CheckoutPanel";
import { LoginCard } from "./components/LoginCard";
import { MessageList } from "./components/MessageList";
import {
  type Cart,
  type Category,
  type Confirmation,
  type Order,
  type SessionInfo,
  type User,
  api,
  yen,
} from "./lib/api";
import { streamChat } from "./lib/sse";
import {
  type Entry,
  categoriesFrom,
  entriesFromStored,
  nextKey,
  productsFrom,
} from "./lib/transcript";

const EMPTY_CART: Cart = { items: [], item_count: 0, total_jpy: 0 };

export default function App() {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [cart, setCart] = useState<Cart | null>(null);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [decision, setDecision] = useState<string | null>(null);
  const [order, setOrder] = useState<Order | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [model, setModel] = useState("");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  // Identifies the assistant bubble currently being streamed into, so deltas
  // append to it instead of creating a bubble per token.
  const streaming = useRef<string | null>(null);

  const fail = useCallback((reason: unknown) => {
    notifications.show({
      color: "red",
      message: reason instanceof Error ? reason.message : String(reason),
    });
  }, []);

  const applySession = useCallback((info: SessionInfo) => {
    setUser(info.user ?? null);
    setCart(info.cart ?? null);
    setConfirmation(info.confirmation ?? null);
    setDecision(info.confirmation_decision ?? null);
    setOrder(info.order ?? null);
    setEntries(entriesFromStored(info.transcript ?? []));
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const health = await api.health();
        if (health.model) setModel(health.model);
      } catch {
        /* the badge is cosmetic */
      }
      try {
        const info = await api.session();
        if (info.authenticated) applySession(info);
      } catch {
        /* not signed in */
      } finally {
        setReady(true);
      }
    })();
  }, [applySession]);

  const push = useCallback((entry: Entry) => setEntries((current) => [...current, entry]), []);

  async function signIn(name: string, email: string) {
    const info = await api.login(name, email);
    applySession(info);
    if (!info.transcript?.length) {
      push({
        kind: "assistant",
        key: nextKey("hello"),
        text: "You are signed in to the local demo. Would you like to shop or view operations?",
      });
    }
  }

  async function signOut() {
    try {
      await api.logout();
    } catch {
      /* the cookie is cleared server-side either way */
    }
    setUser(null);
    setCart(null);
    setConfirmation(null);
    setDecision(null);
    setOrder(null);
    setEntries([]);
  }

  async function newChat() {
    try {
      await api.clearChat();
      setEntries([]);
    } catch (reason) {
      fail(reason);
    }
  }

  function handleEvent(event: { type: string; [key: string]: unknown }) {
    if (event.type === "assistant_delta") {
      const text = (event.text as string) || "";
      setEntries((current) => {
        const last = current[current.length - 1];
        if (streaming.current && last?.kind === "assistant" && last.key === streaming.current) {
          return [...current.slice(0, -1), { ...last, text: last.text + text }];
        }
        const key = nextKey("assistant");
        streaming.current = key;
        return [...current, { kind: "assistant", key, text }];
      });
    } else if (event.type === "tool_started") {
      streaming.current = null;
      push({ kind: "tool", key: nextKey("tool"), tool: (event.tool as string) || "unknown" });
    } else if (event.type === "tool_result") {
      const result = (event.result as Record<string, unknown>) || {};
      if (result.cart) setCart(result.cart as Cart);
      if (result.confirmation) {
        setConfirmation(result.confirmation as Confirmation);
        setDecision(null);
      }
      if (result.order) setOrder(result.order as Order);
      if (result._ops_request) {
        push({ kind: "identity", key: nextKey("identity"), id: (result._ops_request as { id: string }).id });
        return;
      }
      if (result._mcp_app) {
        push({ kind: "app", key: nextKey("app"), descriptor: result._mcp_app as AppDescriptor, result });
        return;
      }
      const products = productsFrom(result);
      if (products.length) push({ kind: "products", key: nextKey("products"), products });
      const categories = categoriesFrom(result);
      if (categories.length) push({ kind: "categories", key: nextKey("categories"), categories });
    } else if (event.type === "error") {
      streaming.current = null;
      push({
        kind: "assistant",
        key: nextKey("error"),
        text: (event.message as string) || "Chat request failed.",
      });
    } else if (event.type === "done") {
      streaming.current = null;
    }
  }

  useEffect(() => {
    const onResult = (event: Event) => {
      const value = (event as CustomEvent).detail;
      if (value.cart) setCart(value.cart);
      if (["add_to_cart", "remove_cart_item"].includes(value._tool)) { setConfirmation(null); setOrder(null); setDecision(null); }
      if (value.confirmation) { setConfirmation(value.confirmation); setDecision(null); }
      if (value.order) setOrder(value.order);
      if (value.decision) { setDecision(value.decision); if (value.decision === "approve") setCart(EMPTY_CART); }
    };
    window.addEventListener("mcp-app-result", onResult);
    return () => window.removeEventListener("mcp-app-result", onResult);
  }, []);

  async function send(override?: string) {
    const value = (override ?? input).trim();
    if (!value || busy) return;
    if (override === undefined) setInput("");
    push({ kind: "user", key: nextKey("user"), text: value });
    streaming.current = null;
    setBusy(true);
    try {
      await streamChat(value, handleEvent);
    } catch (reason) {
      push({
        kind: "assistant",
        key: nextKey("error"),
        text: reason instanceof Error ? reason.message : String(reason),
      });
    } finally {
      streaming.current = null;
      setBusy(false);
    }
  }

  // Clicking a category chip asks for that category by slug, which
  // search_products matches exactly -- no dependence on the model
  // transliterating a Japanese display name.
  function pickCategory(category: Category) {
    void send(`Show me the products in the ${category.slug} category.`);
  }

  async function addToCart(productId: number, sizeId: number, quantity: number) {
    try {
      const result = await api.addCartItem(productId, sizeId, quantity);
      setCart(result.cart);
      setConfirmation(null);
      setOrder(null);
      push({
        kind: "assistant",
        key: nextKey("cart"),
        text: `${result.quote.product_name} added — ${yen(result.quote.subtotal_jpy)}.`,
      });
    } catch (reason) {
      fail(reason);
    }
  }

  async function removeFromCart(itemId: number) {
    try {
      const result = await api.removeCartItem(itemId);
      setCart(result.cart);
      setConfirmation(null);
    } catch (reason) {
      fail(reason);
    }
  }

  async function prepareOrder(address: string) {
    try {
      const result = await api.prepareOrder(address);
      setCart(result.cart);
      setConfirmation(result.confirmation);
      setDecision(null);
      setOrder(null);
    } catch (reason) {
      fail(reason);
    }
  }

  async function decide(choice: "approve" | "reject") {
    try {
      const result = await api.decide(choice, confirmation?.review_id);
      setDecision(choice);
      if (choice === "approve") {
        setOrder(result.order ?? null);
        setCart(EMPTY_CART);
        push({
          kind: "assistant",
          key: nextKey("order"),
          text: `Mock order ${result.order?.order_number} confirmed. No money moved.`,
        });
      } else {
        push({
          kind: "assistant",
          key: nextKey("order"),
          text: "Mock order rejected. Your cart was preserved.",
        });
      }
    } catch (reason) {
      fail(reason);
    }
  }

  if (!ready) {
    return (
      <Group justify="center" mt="20vh">
        <Loader />
      </Group>
    );
  }

  return (
    <Container size="xl" py="lg">
      <Group justify="space-between" align="flex-start" mb="md">
        <div>
          <Text size="xs" fw={800} c="raksul.6" style={{ letterSpacing: "0.12em" }}>
            LOCAL OLLAMA + MCP
          </Text>
          <Title order={1} size="h2">
            Stockroom assistant
          </Title>
        </div>
        <Group gap="xs">
          {model && <Badge variant="default">{model}</Badge>}
          {user && (
            <>
              <Button variant="default" size="xs" onClick={newChat}>
                New chat
              </Button>
              <Button variant="default" size="xs" onClick={signOut}>
                Log out
              </Button>
            </>
          )}
        </Group>
      </Group>

      {!user ? (
        <LoginCard onSignIn={signIn} />
      ) : (
        <Grid align="flex-start">
          <Grid.Col span={{ base: 12, md: 8 }}>
            <Paper radius="lg" style={{ overflow: "hidden" }}>
              <Text size="xs" c="dimmed" px="md" py="xs" bg="gray.0">
                Demo user: {user.name} · {user.email}
              </Text>
              <MessageList
                entries={entries}
                onAdd={addToCart}
                onPickCategory={pickCategory}
                busy={busy}
              />
              <Group
                gap="xs"
                p="md"
                align="flex-end"
                wrap="nowrap"
                style={{ borderTop: "1px solid var(--mantine-color-default-border)" }}
              >
                <Textarea
                  flex={1}
                  autosize
                  minRows={2}
                  maxRows={6}
                  maxLength={4000}
                  disabled={busy}
                  placeholder="Ask for products, an ops dashboard, orders, or users…"
                  value={input}
                  onChange={(event) => setInput(event.currentTarget.value)}
                  onKeyDown={(event) => {
                    // Enter sends; Shift+Enter is a newline.
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      void send();
                    }
                  }}
                />
                <Button onClick={() => void send()} loading={busy}>
                  Send
                </Button>
              </Group>
            </Paper>
          </Grid.Col>

          <Grid.Col span={{ base: 12, md: 4 }}>
            <Stack gap="md">
              <CartPanel cart={cart} onRemove={removeFromCart} onPrepare={prepareOrder} />
              <CheckoutPanel
                confirmation={confirmation}
                decision={decision}
                order={order}
                onDecide={decide}
              />
            </Stack>
          </Grid.Col>
        </Grid>
      )}
    </Container>
  );
}
