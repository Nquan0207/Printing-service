import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Card,
  Center,
  Drawer,
  Group,
  Image,
  Indicator,
  Loader,
  Modal,
  NumberInput,
  Paper,
  SegmentedControl,
  SimpleGrid,
  Select,
  Stack,
  Text,
  Textarea,
  TextInput,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { api, yen, type Cart, type Category, type Product, type ProductList } from "../lib/api";

export default function Shop() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [list, setList] = useState<ProductList | null>(null);
  const [cart, setCart] = useState<Cart | null>(null);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [maxPrice, setMaxPrice] = useState<string | number>("");
  const [loading, setLoading] = useState(true);
  const [cartOpen, cartHandlers] = useDisclosure(false);
  const [detailId, setDetailId] = useState<number | null>(null);

  const [debouncedQuery] = useDebouncedValue(query, 250);
  const [debouncedPrice] = useDebouncedValue(maxPrice, 400);

  const refreshCart = useCallback(async () => setCart(await api.cart()), []);

  useEffect(() => {
    api.categories().then((r) => setCategories(r.categories)).catch(() => {});
    refreshCart().catch(() => {});
  }, [refreshCart]);

  useEffect(() => {
    setLoading(true);
    api
      .products({
        q: debouncedQuery,
        category: category ?? "",
        max_price: debouncedPrice === "" ? undefined : Number(debouncedPrice),
        limit: 60,
        per_category: 8,
      })
      .then(setList)
      .catch((e) => notifications.show({ color: "red", message: e.message }))
      .finally(() => setLoading(false));
  }, [debouncedQuery, category, debouncedPrice]);

  return (
    <>
      <Paper p="sm" mb="lg" radius="md">
        <Group gap="sm" wrap="wrap">
          <TextInput
            placeholder="Search products…"
            value={query}
            onChange={(e) => setQuery(e.currentTarget.value)}
            style={{ flex: 1, minWidth: 220 }}
          />
          <Select
            placeholder="All categories"
            clearable
            value={category}
            onChange={setCategory}
            data={categories.map((c) => ({ value: c.slug, label: c.name }))}
            w={230}
          />
          <NumberInput
            placeholder="Max ¥"
            min={0}
            step={100}
            value={maxPrice}
            onChange={setMaxPrice}
            w={130}
            hideControls
          />
          <Indicator label={cart?.item_count ?? 0} size={18} disabled={!cart?.item_count}>
            <Button onClick={cartHandlers.open} variant="filled">
              Cart
            </Button>
          </Indicator>
        </Group>
      </Paper>

      {loading && !list && (
        <Center py="xl">
          <Loader />
        </Center>
      )}

      {list && list.count === 0 && (
        <Center py={80}>
          <Stack align="center" gap={4}>
            <Title order={3}>No products match</Title>
            <Text c="dimmed" size="sm">
              Try a different search or clear the filters.
            </Text>
          </Stack>
        </Center>
      )}

      <Stack gap="xl">
        {list?.groups.map((g) => (
          <Box key={g.category.id}>
            <Group gap="xs" mb="sm">
              <Title order={4}>{g.category.name}</Title>
              <Badge variant="light" color="gray" size="sm">
                {g.count}
              </Badge>
            </Group>
            <Box
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))",
                gap: "var(--mantine-spacing-md)",
              }}
            >
              {g.products.map((p) => (
                <ProductCard
                  key={p.id}
                  product={p}
                  onAdded={refreshCart}
                  onOpen={() => setDetailId(p.id)}
                />
              ))}
            </Box>
          </Box>
        ))}
      </Stack>

      <ProductDetail
        productId={detailId}
        onClose={() => setDetailId(null)}
        onAdded={refreshCart}
      />

      <CartDrawer
        opened={cartOpen}
        onClose={cartHandlers.close}
        cart={cart}
        onChanged={refreshCart}
      />
    </>
  );
}

function ProductCard({
  product,
  onAdded,
  onOpen,
}: {
  product: Product;
  onAdded: () => Promise<void>;
  onOpen: () => void;
}) {
  const [sizeId, setSizeId] = useState(String(product.sizes[0]?.id ?? ""));
  const [qty, setQty] = useState<string | number>(1);
  const [busy, setBusy] = useState(false);

  const size = useMemo(
    () => product.sizes.find((s) => String(s.id) === sizeId) ?? product.sizes[0],
    [product.sizes, sizeId],
  );
  const quantity = Math.max(1, Number(qty) || 1);

  async function add() {
    if (!size) return;
    setBusy(true);
    try {
      await api.addToCart(product.id, size.id, quantity);
      await onAdded();
      notifications.show({
        color: "teal",
        title: "Added to cart",
        message: `${product.name} · ${size.size_name} × ${quantity}`,
      });
    } catch (e) {
      notifications.show({ color: "red", message: e instanceof Error ? e.message : "Failed" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card padding="sm" radius="md">
      <Card.Section
        className="thumb"
        h={150}
        bg="var(--mantine-color-default-hover)"
        onClick={onOpen}
        style={{ display: "grid", placeItems: "center", overflow: "hidden", cursor: "pointer" }}
      >
        {product.images[0] ? (
          <img src={product.images[0]} alt={product.name} loading="lazy" />
        ) : (
          <Text size="xs" c="dimmed">
            No image
          </Text>
        )}
      </Card.Section>

      <Stack gap={6} mt="sm" style={{ flex: 1 }}>
        <Text
          size="sm"
          fw={500}
          lineClamp={2}
          title={product.name}
          onClick={onOpen}
          style={{ minHeight: "2.6em", cursor: "pointer" }}
        >
          {product.name}
        </Text>
        {product.brand && (
          <Text size="xs" c="dimmed">
            {product.brand}
          </Text>
        )}

        <SegmentedControl
          size="xs"
          fullWidth
          value={sizeId}
          onChange={setSizeId}
          data={product.sizes.map((s) => ({ value: String(s.id), label: s.size_name }))}
        />

        <Group justify="space-between" align="center" gap="xs" wrap="nowrap">
          <Text fw={700}>{size ? yen(size.unit_price_jpy) : "—"}</Text>
          <NumberInput
            size="xs"
            w={64}
            min={1}
            value={qty}
            onChange={setQty}
            hideControls
            aria-label="Quantity"
          />
          <Button size="xs" onClick={add} loading={busy} disabled={!size}>
            Add
          </Button>
        </Group>

        {size && quantity > 1 && (
          <Text size="xs" c="dimmed">
            {quantity} × = {yen(size.unit_price_jpy * quantity)}
          </Text>
        )}

        {product.images.length > 1 && (
          <Text size="xs" c="dimmed" onClick={onOpen} style={{ cursor: "pointer" }}>
            +{product.images.length - 1} more photo{product.images.length > 2 ? "s" : ""}
          </Text>
        )}
      </Stack>
    </Card>
  );
}

function CartDrawer({
  opened,
  onClose,
  cart,
  onChanged,
}: {
  opened: boolean;
  onClose: () => void;
  cart: Cart | null;
  onChanged: () => Promise<void>;
}) {
  const [address, setAddress] = useState("東京都渋谷区1-2-3");
  const [placing, setPlacing] = useState(false);
  const [placed, setPlaced] = useState<string | null>(null);

  async function checkout() {
    setPlacing(true);
    try {
      const order = await api.placeOrder(address);
      localStorage.setItem("stockroom.lastOrder", order.order_number);
      setPlaced(order.order_number);
      await onChanged();
    } catch (e) {
      notifications.show({ color: "red", message: e instanceof Error ? e.message : "Failed" });
    } finally {
      setPlacing(false);
    }
  }

  return (
    <Drawer
      opened={opened}
      onClose={() => {
        setPlaced(null);
        onClose();
      }}
      position="right"
      size={430}
      title={<Text fw={600}>Your cart</Text>}
    >
      {placed ? (
        <Stack align="center" py="xl" gap="xs">
          <ThemeIcon size={54} radius="xl" color="teal" variant="light">
            ✓
          </ThemeIcon>
          <Title order={4}>Order placed</Title>
          <Text ff="monospace" c="raksul" fw={600}>
            {placed}
          </Text>
          <Text size="sm" c="dimmed">
            Your cart has been cleared.
          </Text>
          <Button
            variant="default"
            mt="sm"
            onClick={() => {
              setPlaced(null);
              onClose();
            }}
          >
            Keep shopping
          </Button>
        </Stack>
      ) : !cart || cart.items.length === 0 ? (
        <Text c="dimmed" py="xl" ta="center">
          Your cart is empty.
        </Text>
      ) : (
        <Stack gap="md">
          <Stack gap="sm">
            {cart.items.map((i) => (
              <Group key={i.id} gap="sm" wrap="nowrap" align="center">
                <Image
                  src={i.image ?? undefined}
                  w={46}
                  h={46}
                  fit="contain"
                  radius="sm"
                  bg="var(--mantine-color-default-hover)"
                  fallbackSrc="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E"
                />
                <Box style={{ flex: 1, minWidth: 0 }}>
                  <Text size="sm" lineClamp={1}>
                    {i.product_name}
                  </Text>
                  <Text size="xs" c="dimmed">
                    Size {i.size_name} · {i.quantity} × {yen(i.unit_price_jpy)}
                  </Text>
                </Box>
                <Text fw={600} size="sm">
                  {yen(i.subtotal_jpy)}
                </Text>
                <ActionIcon
                  variant="subtle"
                  color="gray"
                  aria-label="Remove"
                  onClick={async () => {
                    await api.removeCartItem(i.id);
                    await onChanged();
                  }}
                >
                  ✕
                </ActionIcon>
              </Group>
            ))}
          </Stack>

          <Group justify="space-between" pt="sm" style={{ borderTop: "1px solid var(--mantine-color-default-border)" }}>
            <Text c="dimmed">Total</Text>
            <Text fw={700} fz="lg">
              {yen(cart.total_jpy)}
            </Text>
          </Group>
          <Text size="xs" c="dimmed">
            Mock pricing — no tax, shipping, or volume discounts.
          </Text>

          <Textarea
            label="Shipping address"
            value={address}
            onChange={(e) => setAddress(e.currentTarget.value)}
            autosize
            minRows={2}
          />

          <Button
            size="md"
            onClick={checkout}
            loading={placing}
            disabled={!address.trim()}
            fullWidth
          >
            Place order · {yen(cart.total_jpy)}
          </Button>
        </Stack>
      )}
    </Drawer>
  );
}

/**
 * Product detail. Search results omit `description` and the card only ever
 * shows images[0], so this refetches the full product to reach the rest.
 */
function ProductDetail({
  productId,
  onClose,
  onAdded,
}: {
  productId: number | null;
  onClose: () => void;
  onAdded: () => Promise<void>;
}) {
  const [product, setProduct] = useState<Product | null>(null);
  const [active, setActive] = useState(0);
  const [sizeId, setSizeId] = useState("");
  const [qty, setQty] = useState<string | number>(1);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (productId === null) return;
    setProduct(null);
    setActive(0);
    api
      .product(productId)
      .then((p) => {
        setProduct(p);
        setSizeId(String(p.sizes[0]?.id ?? ""));
      })
      .catch((e) => notifications.show({ color: "red", message: e.message }));
  }, [productId]);

  const size = product?.sizes.find((s) => String(s.id) === sizeId) ?? product?.sizes[0];
  const quantity = Math.max(1, Number(qty) || 1);

  async function add() {
    if (!product || !size) return;
    setBusy(true);
    try {
      await api.addToCart(product.id, size.id, quantity);
      await onAdded();
      notifications.show({
        color: "teal",
        title: "Added to cart",
        message: `${product.name} · ${size.size_name} × ${quantity}`,
      });
      onClose();
    } catch (e) {
      notifications.show({ color: "red", message: e instanceof Error ? e.message : "Failed" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      opened={productId !== null}
      onClose={onClose}
      size="lg"
      title={<Text fw={600}>Product details</Text>}
    >
      {!product ? (
        <Center py="xl">
          <Loader />
        </Center>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg">
          <Stack gap="xs">
            <Box
              className="thumb"
              h={260}
              bg="var(--mantine-color-default-hover)"
              style={{ display: "grid", placeItems: "center", overflow: "hidden", borderRadius: 8 }}
            >
              {product.images[active] ? (
                <img src={product.images[active]} alt={product.name} />
              ) : (
                <Text size="sm" c="dimmed">
                  No image
                </Text>
              )}
            </Box>
            {product.images.length > 1 && (
              <Group gap={6}>
                {product.images.map((src, i) => (
                  <Box
                    key={src}
                    className="thumb"
                    w={56}
                    h={56}
                    onClick={() => setActive(i)}
                    bg="var(--mantine-color-default-hover)"
                    style={{
                      display: "grid",
                      placeItems: "center",
                      overflow: "hidden",
                      borderRadius: 6,
                      cursor: "pointer",
                      outline:
                        i === active ? "2px solid var(--mantine-color-raksul-6)" : "none",
                    }}
                  >
                    <img src={src} alt="" />
                  </Box>
                ))}
              </Group>
            )}
          </Stack>

          <Stack gap="sm">
            <div>
              <Text fw={600}>{product.name}</Text>
              {product.brand && (
                <Text size="xs" c="dimmed">
                  {product.brand} · {product.category.name}
                </Text>
              )}
            </div>

            {product.description && (
              <Text size="sm" c="dimmed" lineClamp={6}>
                {product.description}
              </Text>
            )}

            <SegmentedControl
              size="xs"
              fullWidth
              value={sizeId}
              onChange={setSizeId}
              data={product.sizes.map((s) => ({ value: String(s.id), label: s.size_name }))}
            />

            <Group justify="space-between" align="center">
              <Text fz="xl" fw={700}>
                {size ? yen(size.unit_price_jpy) : "—"}
              </Text>
              <NumberInput size="sm" w={80} min={1} value={qty} onChange={setQty} hideControls />
            </Group>

            <Button onClick={add} loading={busy} disabled={!size} fullWidth>
              Add to cart{size && quantity > 1 ? ` · ${yen(size.unit_price_jpy * quantity)}` : ""}
            </Button>
          </Stack>
        </SimpleGrid>
      )}
    </Modal>
  );
}
