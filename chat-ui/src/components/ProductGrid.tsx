import { useState } from "react";
import {
  Box,
  Button,
  Card,
  Center,
  Group,
  Image,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Text,
} from "@mantine/core";
import { type Product, mediaUrl, yen } from "../lib/api";

type Props = {
  products: Product[];
  onAdd: (productId: number, sizeId: number, quantity: number) => Promise<void>;
};

function ProductCard({ product, onAdd }: { product: Product; onAdd: Props["onAdd"] }) {
  const sizes = product.sizes ?? [];
  const [sizeId, setSizeId] = useState<string | null>(sizes[0] ? String(sizes[0].id) : null);
  const [quantity, setQuantity] = useState<number>(1);
  const [busy, setBusy] = useState(false);
  const image = mediaUrl(product.images?.[0]);

  async function add() {
    if (!sizeId) return;
    setBusy(true);
    try {
      await onAdd(product.id, Number(sizeId), quantity);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card padding="sm" radius="md">
      <Card.Section>
        {image ? (
          <Image src={image} alt={product.name} h={140} fit="contain" bg="gray.0" />
        ) : (
          <Center h={140} bg="gray.0">
            <Text size="xs" c="dimmed">
              No image
            </Text>
          </Center>
        )}
      </Card.Section>
      <Stack gap={6} mt="sm">
        <Text fw={600} size="sm" lineClamp={2} title={product.name}>
          {product.name}
        </Text>
        <Text size="xs" c="dimmed">
          {product.category?.name || product.brand || "Stockroom"}
        </Text>
        <Text fw={800}>From {yen(product.base_price_jpy)}</Text>
        <Group gap="xs" grow wrap="nowrap">
          <Select
            size="xs"
            aria-label="Size"
            data={sizes.map((size) => ({
              value: String(size.id),
              label: `${size.size_name} · ${yen(size.unit_price_jpy)}`,
            }))}
            value={sizeId}
            onChange={setSizeId}
            allowDeselect={false}
            disabled={!sizes.length}
          />
          <Box maw={70}>
            <NumberInput
              size="xs"
              aria-label="Quantity"
              min={1}
              max={100}
              clampBehavior="strict"
              value={quantity}
              onChange={(value) => setQuantity(typeof value === "number" ? value : 1)}
            />
          </Box>
        </Group>
        <Button size="xs" onClick={add} loading={busy} disabled={!sizes.length}>
          Quote and add
        </Button>
      </Stack>
    </Card>
  );
}

export function ProductGrid({ products, onAdd }: Props) {
  if (!products.length) return null;
  return (
    <SimpleGrid cols={{ base: 1, xs: 2, md: 3 }} spacing="sm" my="sm">
      {products.map((product) => (
        <ProductCard key={product.id} product={product} onAdd={onAdd} />
      ))}
    </SimpleGrid>
  );
}
