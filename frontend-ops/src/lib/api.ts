// Thin client over the Go API. Every call goes through request() so the
// error envelope is unwrapped in exactly one place.

export type Category = { id: number; slug: string; name: string };

export type Size = {
  id: number;
  size_name: string;
  price_adjustment_jpy: number;
  unit_price_jpy: number;
};

export type Product = {
  id: number;
  source_product_id?: string;
  name: string;
  brand: string | null;
  description?: string | null;
  category: Category;
  base_price_jpy: number;
  sizes: Size[];
  images: string[];
};

export type CategoryGroup = { category: Category; count: number; products: Product[] };
export type ProductList = { groups: CategoryGroup[]; count: number };

export type CartItem = {
  id: number;
  product_id: number;
  product_name: string;
  size_id: number;
  size_name: string;
  image: string | null;
  quantity: number;
  unit_price_jpy: number;
  subtotal_jpy: number;
};
export type Cart = { items: CartItem[]; item_count: number; total_jpy: number };

export type OrderItem = {
  product_id: number | null;
  product_name: string;
  size_name: string;
  quantity: number;
  unit_price_jpy: number;
  subtotal_jpy: number;
};
export type Order = {
  order_number: string;
  status: string;
  shipping_address: string;
  total_jpy: number;
  items: OrderItem[];
  created_at: string;
};
export type AdminOrder = Order & {
  user_id: number;
  user_name: string;
  user_email: string;
};

export type User = {
  user_id: number;
  email: string;
  name: string;
  is_admin: boolean;
  created: boolean;
};

export type AdminUser = {
  id: number;
  name: string;
  email: string;
  created_at: string;
  is_admin: boolean;
  cart_lines: number;
  orders: number;
  spent_jpy: number;
};

export type Stats = {
  totals: {
    products: number;
    active_products: number;
    categories: number;
    sizes: number;
    images: number;
    users: number;
    orders: number;
    revenue_jpy: number;
    open_cart_lines: number;
    cancelled_orders: number;
  };
  products_by_category: { slug: string; name: string; count: number }[];
  orders_by_day: { date: string; orders: number; revenue_jpy: number }[];
  top_products: { product_id: number | null; product_name: string; quantity: number; revenue_jpy: number }[];
  price_buckets: { label: string; count: number }[];
};

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

/** The signed-in user id, sent as X-Stockroom-User on every call. */
let userId: number | null = null;
export function setUserId(id: number | null) {
  userId = id;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (userId !== null) headers.set("X-Stockroom-User", String(userId));

  const res = await fetch(`/api/v1${path}`, { ...init, headers });
  if (res.status === 204) return undefined as T;

  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const err = body?.error ?? {};
    throw new ApiError(res.status, err.code ?? "unknown", err.message ?? res.statusText);
  }
  return body as T;
}

export const api = {
  config: () => request<{ shop_enabled: boolean }>("/config"),
  login: (email: string, name?: string) =>
    request<User>("/login", { method: "POST", body: JSON.stringify({ email, name }) }),

  categories: () => request<{ categories: Category[] }>("/categories"),
  products: (params: Record<string, string | number | undefined>) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") q.set(k, String(v));
    }
    return request<ProductList>(`/products?${q}`);
  },
  product: (id: number) => request<Product>(`/products/${id}`),
  quote: (product_id: number, size_id: number, quantity: number) =>
    request<{ unit_price_jpy: number; subtotal_jpy: number; notes: string[] }>("/quote", {
      method: "POST",
      body: JSON.stringify({ product_id, size_id, quantity }),
    }),

  cart: () => request<Cart>("/cart"),
  addToCart: (product_id: number, size_id: number, quantity: number) =>
    request<Cart>("/cart/items", {
      method: "POST",
      body: JSON.stringify({ product_id, size_id, quantity }),
    }),
  removeCartItem: (id: number) => request<Cart>(`/cart/items/${id}`, { method: "DELETE" }),

  placeOrder: (shipping_address: string) =>
    request<Order>("/orders", { method: "POST", body: JSON.stringify({ shipping_address }) }),
  order: (orderNumber: string) => request<Order>(`/orders/${orderNumber}`),

  admin: {
    stats: (days = 30) => request<Stats>(`/admin/stats?days=${days}`),
    orders: (status?: string) =>
      request<{ orders: AdminOrder[]; total: number }>(
        `/admin/orders?limit=100${status ? `&status=${status}` : ""}`,
      ),
    updateOrder: (orderNumber: string, status: string) =>
      request<unknown>(`/admin/orders/${orderNumber}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }),
    users: () => request<{ users: AdminUser[]; total: number }>("/admin/users?limit=200"),
    // Category-first, same shape as the shop endpoint.
    products: (q?: string) =>
      request<ProductList>(`/admin/products${q ? `?q=${encodeURIComponent(q)}` : ""}`),
    updateProduct: (
      id: number,
      patch: { name?: string; base_price_jpy?: number; is_active?: boolean; description?: string },
    ) => request<unknown>(`/admin/products/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
    updateSize: (id: number, patch: { size_name?: string; price_adjustment_jpy?: number }) =>
      request<unknown>(`/admin/sizes/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
    deleteProduct: (id: number) => request<void>(`/admin/products/${id}`, { method: "DELETE" }),
  },
};

export const yen = (n: number) => `¥${n.toLocaleString("ja-JP")}`;
