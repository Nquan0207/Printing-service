// Thin client over the Python chat service. Every call goes through request()
// so FastAPI's {"detail": ...} error shape is unwrapped in exactly one place.

export type User = {
  user_id: number;
  email: string;
  name: string;
  is_admin: boolean;
  created: boolean;
};

export type Category = {
  id: number;
  slug: string;
  name: string;
  product_count?: number;
};

export type Size = { id: number; size_name: string; unit_price_jpy: number };

export type Product = {
  id: number;
  name: string;
  brand: string | null;
  category: Category | null;
  base_price_jpy: number;
  sizes: Size[];
  images: string[];
};

export type CartItem = {
  id: number;
  product_name: string;
  size_name: string;
  quantity: number;
  subtotal_jpy: number;
};

export type Cart = { items: CartItem[]; item_count: number; total_jpy: number };

export type Confirmation = { shipping_address: string; expires_at: string };

export type Order = { order_number: string; total_jpy: number };

/** One stored line, as chat_messages rows come back through the chat service. */
export type StoredMessage = {
  id: number;
  role: "user" | "assistant" | "tool";
  content: string;
  tool_name: string | null;
  payload: Record<string, unknown> | null;
  created_at: string;
};

export type SessionInfo = {
  authenticated: boolean;
  user?: User;
  cart?: Cart | null;
  confirmation?: Confirmation | null;
  confirmation_decision?: string | null;
  order?: Order | null;
  transcript?: StoredMessage[];
};

export type Health = { status: string; model?: string; ollama?: string; stockroom_api?: string };

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  let body: any = {};
  try {
    body = await response.json();
  } catch {
    /* 204 and empty bodies are fine */
  }
  if (!response.ok) throw new Error(body?.detail || `Request failed (${response.status})`);
  return body as T;
}

export const api = {
  health: () => request<Health>("/healthz"),
  session: () => request<SessionInfo>("/api/session"),
  login: (name: string, email: string) =>
    request<SessionInfo>("/api/session/login", {
      method: "POST",
      body: JSON.stringify({ name, email }),
    }),
  logout: () => request<{ status: string }>("/api/session", { method: "DELETE" }),
  clearChat: () => request<{ status: string }>("/api/chat/messages", { method: "DELETE" }),
  addCartItem: (product_id: number, size_id: number, quantity: number) =>
    request<{ quote: { product_name: string; subtotal_jpy: number }; cart: Cart }>(
      "/api/cart/items",
      { method: "POST", body: JSON.stringify({ product_id, size_id, quantity }) },
    ),
  removeCartItem: (itemId: number) =>
    request<{ cart: Cart }>(`/api/cart/items/${itemId}`, { method: "DELETE" }),
  prepareOrder: (shipping_address: string) =>
    request<{ cart: Cart; confirmation: Confirmation }>("/api/order/prepare", {
      method: "POST",
      body: JSON.stringify({ shipping_address }),
    }),
  decide: (decision: "approve" | "reject") =>
    request<{ order?: Order }>("/api/order/decision", {
      method: "POST",
      body: JSON.stringify({ decision }),
    }),
};

/** ¥ with thousands separators, or an em dash when the value is not an integer. */
export function yen(value: unknown): string {
  return Number.isInteger(value) ? `¥${(value as number).toLocaleString()}` : "—";
}

/**
 * Keep only same-origin /media/products/... paths.
 *
 * Tool results are built from crawled product text, so an absolute URL in an
 * image field must never become an <img src> pointing off this origin.
 */
export function mediaUrl(value: unknown): string {
  if (typeof value !== "string") return "";
  try {
    const url = new URL(value, window.location.origin);
    return url.pathname.startsWith("/media/products/") ? url.pathname : "";
  } catch {
    return "";
  }
}
