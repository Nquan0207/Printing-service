import { Badge, Group, Stack, Text } from "@mantine/core";
import type { Category } from "../lib/api";

type Props = {
  categories: Category[];
  /** Runs a follow-up turn for one category; disabled while a turn is in flight. */
  onPick: (category: Category) => void;
  disabled: boolean;
};

export function CategoryChips({ categories, onPick, disabled }: Props) {
  if (!categories.length) return null;
  return (
    <Stack gap={6} my="sm">
      <Text size="xs" c="dimmed">
        Pick a category to see its products
      </Text>
      <Group gap="xs">
        {categories.map((category) => (
          <Badge
            key={category.id}
            variant="light"
            size="lg"
            tt="none"
            style={{ cursor: disabled ? "default" : "pointer" }}
            onClick={() => !disabled && onPick(category)}
          >
            {category.name}
            {typeof category.product_count === "number" ? ` · ${category.product_count}` : ""}
          </Badge>
        ))}
      </Group>
    </Stack>
  );
}
