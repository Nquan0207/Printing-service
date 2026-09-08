// The chat transcript the browser renders, and how a stored transcript maps
// back onto it after a reload.

import type { Category, Product, StoredMessage } from "./api";

import type { AppDescriptor } from "../components/MCPApp";

export type Entry =
  | { kind: "app"; key: string; descriptor: AppDescriptor; result: Record<string, unknown>; restored?: boolean }
  | { kind: "identity"; key: string; id: string }
  | { kind: "user"; key: string; text: string }
  | { kind: "assistant"; key: string; text: string }
  | { kind: "tool"; key: string; tool: string }
  | { kind: "products"; key: string; products: Product[] }
  | { kind: "categories"; key: string; categories: Category[] };

let counter = 0;
/** Keys only have to be unique within one mounted list, not stable across reloads. */
export function nextKey(prefix: string): string {
  counter += 1;
  return `${prefix}-${counter}`;
}

/**
 * Pull the products out of a tool result.
 *
 * search_products returns category groups; get_product returns one product.
 * Anything else contributes no cards.
 */
export function productsFrom(result: Record<string, unknown> | null | undefined): Product[] {
  if (!result) return [];
  const groups = (result as { groups?: { products?: Product[] }[] }).groups;
  if (Array.isArray(groups)) return groups.flatMap((group) => group.products ?? []);
  const single = (result as { product?: Product }).product;
  return single ? [single] : [];
}

/**
 * Pull the categories out of a list_categories result.
 *
 * Without this the tool renders as a bare "used a tool" note, while the model
 * cheerfully tells the user to click categories that were never drawn.
 */
export function categoriesFrom(result: Record<string, unknown> | null | undefined): Category[] {
  const categories = (result as { categories?: Category[] } | null)?.categories;
  return Array.isArray(categories) ? categories : [];
}

/**
 * Rebuild the visible conversation from what Postgres kept.
 *
 * A stored tool line becomes the same pair the live stream produces: the
 * "using tool" note, then its product cards if it had any.
 */
export function entriesFromStored(messages: StoredMessage[]): Entry[] {
  const entries: Entry[] = [];
  for (const message of messages) {
    if (message.role === "user") {
      entries.push({ kind: "user", key: `m${message.id}`, text: message.content });
    } else if (message.role === "assistant") {
      entries.push({ kind: "assistant", key: `m${message.id}`, text: message.content });
    } else {
      entries.push({
        kind: "tool",
        key: `m${message.id}`,
        tool: message.tool_name ?? "unknown",
      });
      const app = message.payload?._mcp_app as AppDescriptor | undefined;
      if (app) {
        entries.push({ kind: "app", key: `m${message.id}-app`, descriptor: app, result: message.payload!, restored: true });
        continue;
      }
      const opsRequest = message.payload?._ops_request as { id?: string } | undefined;
      if (opsRequest?.id) {
        entries.push({ kind: "identity", key: `m${message.id}-identity`, id: opsRequest.id });
        continue;
      }
      const products = productsFrom(message.payload);
      if (products.length) {
        entries.push({ kind: "products", key: `m${message.id}-p`, products });
      }
      const categories = categoriesFrom(message.payload);
      if (categories.length) {
        entries.push({ kind: "categories", key: `m${message.id}-c`, categories });
      }
    }
  }
  return entries;
}
