import { useEffect, useRef } from "react";
import { Badge, Paper, ScrollArea, Stack, Text } from "@mantine/core";
import type { Category } from "../lib/api";
import type { Entry } from "../lib/transcript";
import { CategoryChips } from "./CategoryChips";
import { MCPApp, OpsRequest } from "./MCPApp";
import { ProductGrid } from "./ProductGrid";

type Props = {
  entries: Entry[];
  onAdd: (productId: number, sizeId: number, quantity: number) => Promise<void>;
  onPickCategory: (category: Category) => void;
  busy: boolean;
};

export function MessageList({ entries, onAdd, onPickCategory, busy }: Props) {
  const viewport = useRef<HTMLDivElement>(null);

  // Follow the newest line, including each streamed token.
  useEffect(() => {
    viewport.current?.scrollTo({ top: viewport.current.scrollHeight });
  }, [entries]);

  return (
    <ScrollArea className="chat-scroll" viewportRef={viewport} p="md" aria-live="polite">
      <Stack gap="sm">
        {entries.map((entry) => {
          if (entry.kind === "app") return <MCPApp key={entry.key} descriptor={entry.descriptor} result={entry.result} restored={entry.restored} />;
          if (entry.kind === "identity") return <OpsRequest key={entry.key} id={entry.id} />;
          if (entry.kind === "products") {
            return <ProductGrid key={entry.key} products={entry.products} onAdd={onAdd} />;
          }
          if (entry.kind === "categories") {
            return (
              <CategoryChips
                key={entry.key}
                categories={entry.categories}
                onPick={onPickCategory}
                disabled={busy}
              />
            );
          }
          if (entry.kind === "tool") {
            return (
              <Badge key={entry.key} variant="outline" color="gray" size="sm" tt="none">
                Using MCP tool: {entry.tool}
              </Badge>
            );
          }
          const isUser = entry.kind === "user";
          return (
            <Paper
              key={entry.key}
              className={`chat-bubble${isUser ? " chat-bubble-user" : ""}`}
              px="md"
              py="xs"
              radius="lg"
              withBorder={!isUser}
              bg={isUser ? "raksul.6" : undefined}
            >
              <Text size="sm" c={isUser ? "white" : undefined}>
                {entry.text}
              </Text>
            </Paper>
          );
        })}
      </Stack>
    </ScrollArea>
  );
}
