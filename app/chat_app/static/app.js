const state = {
  user: null,
  cart: null,
  confirmation: null,
  confirmationDecision: null,
  order: null,
  busy: false,
  currentAssistant: null
};

const $ = selector => document.querySelector(selector);
const loginView = $("#loginView");
const chatView = $("#chatView");
const messages = $("#messages");

function yen(value) {
  return Number.isInteger(value) ? `¥${value.toLocaleString()}` : "—";
}

function setBusy(value) {
  state.busy = value;
  $("#sendButton").disabled = value;
  $("#chatInput").disabled = value;
}

function message(role, text) {
  const node = document.createElement("div");
  node.className = `message ${role}`;
  node.textContent = text;
  messages.append(node);
  messages.scrollTop = messages.scrollHeight;
  return node;
}

function mediaUrl(value) {
  if (typeof value !== "string") return "";
  try {
    const url = new URL(value, window.location.origin);
    return url.pathname.startsWith("/media/products/") ? url.pathname : "";
  } catch (_) {
    return "";
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {"Content-Type": "application/json", ...(options.headers || {})}
  });
  let body = {};
  try { body = await response.json(); } catch (_) {}
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}

function showAuthenticated(authenticated) {
  loginView.hidden = authenticated;
  chatView.hidden = !authenticated;
  $("#logoutButton").hidden = !authenticated;
  if (authenticated && state.user) {
    $("#identity").textContent = `Demo user: ${state.user.name} · ${state.user.email}`;
  }
}

function productsFrom(result) {
  if (Array.isArray(result?.groups)) {
    return result.groups.flatMap(group => group.products || []);
  }
  return result?.product ? [result.product] : [];
}

function renderProducts(result) {
  const products = productsFrom(result);
  if (!products.length) return;
  const wrap = document.createElement("div");
  wrap.className = "rich-result product-grid";

  for (const product of products) {
    const card = document.createElement("article");
    card.className = "product-card";
    const image = mediaUrl(product.images?.[0]);
    if (image) {
      const img = document.createElement("img");
      img.src = image;
      img.alt = product.name || "Product";
      img.addEventListener("error", () => img.replaceWith(placeholder()));
      card.append(img);
    } else {
      card.append(placeholder());
    }

    const body = document.createElement("div");
    body.className = "product-body";
    const title = document.createElement("h3");
    title.textContent = product.name || `Product ${product.id}`;
    const category = document.createElement("p");
    category.textContent = product.category?.name || product.brand || "Stockroom";
    const price = document.createElement("p");
    price.className = "price";
    price.textContent = `From ${yen(product.base_price_jpy)}`;

    const actions = document.createElement("div");
    actions.className = "product-actions";
    const size = document.createElement("select");
    size.setAttribute("aria-label", "Size");
    for (const optionValue of product.sizes || []) {
      const option = document.createElement("option");
      option.value = optionValue.id;
      option.textContent = `${optionValue.size_name} · ${yen(optionValue.unit_price_jpy)}`;
      size.append(option);
    }
    const quantity = document.createElement("input");
    quantity.type = "number";
    quantity.min = "1";
    quantity.max = "100";
    quantity.value = "1";
    quantity.setAttribute("aria-label", "Quantity");
    const add = document.createElement("button");
    add.className = "primary";
    add.textContent = "Quote and add";
    add.disabled = !product.sizes?.length;
    add.addEventListener("click", async () => {
      add.disabled = true;
      try {
        const result = await api("/api/cart/items", {
          method: "POST",
          body: JSON.stringify({
            product_id: product.id,
            size_id: Number(size.value),
            quantity: Number(quantity.value)
          })
        });
        state.cart = result.cart;
        state.confirmation = null;
        state.order = null;
        renderCart();
        message("assistant", `${result.quote.product_name} added — ${yen(result.quote.subtotal_jpy)}.`);
      } catch (error) {
        message("assistant", error.message);
      } finally {
        add.disabled = false;
      }
    });
    actions.append(size, quantity, add);
    body.append(title, category, price, actions);
    card.append(body);
    wrap.append(card);
  }
  messages.append(wrap);
  messages.scrollTop = messages.scrollHeight;
}

function placeholder() {
  const node = document.createElement("div");
  node.className = "image-placeholder";
  node.textContent = "No image";
  return node;
}

function renderCart() {
  const panel = $("#cartPanel");
  panel.replaceChildren();
  const cart = state.cart || {items: [], item_count: 0, total_jpy: 0};
  const title = document.createElement("h2");
  title.textContent = `Cart · ${cart.item_count || 0}`;
  panel.append(title);

  if (!cart.items?.length) {
    const empty = document.createElement("p");
    empty.textContent = "Your local database cart is empty.";
    empty.style.color = "var(--muted)";
    panel.append(empty);
  }

  for (const item of cart.items || []) {
    const line = document.createElement("div");
    line.className = "cart-line";
    const name = document.createElement("strong");
    name.textContent = item.product_name;
    const detail = document.createElement("p");
    detail.textContent = `${item.size_name} · quantity ${item.quantity}`;
    const row = document.createElement("div");
    row.className = "line-actions";
    const subtotal = document.createElement("span");
    subtotal.textContent = yen(item.subtotal_jpy);
    const remove = document.createElement("button");
    remove.className = "danger";
    remove.textContent = "Remove";
    remove.addEventListener("click", async () => {
      try {
        const result = await api(`/api/cart/items/${item.id}`, {method: "DELETE"});
        state.cart = result.cart;
        state.confirmation = null;
        renderCart();
      } catch (error) { message("assistant", error.message); }
    });
    row.append(subtotal, remove);
    line.append(name, detail, row);
    panel.append(line);
  }

  const total = document.createElement("div");
  total.className = "total";
  total.innerHTML = `<span>Total</span><span>${yen(cart.total_jpy)}</span>`;
  panel.append(total);

  const form = document.createElement("form");
  form.className = "checkout-form";
  const address = document.createElement("input");
  address.required = true;
  address.maxLength = 500;
  address.placeholder = "Mock shipping address";
  const review = document.createElement("button");
  review.className = "primary";
  review.textContent = "Review mock order";
  review.disabled = !cart.items?.length;
  form.append(address, review);
  form.addEventListener("submit", async event => {
    event.preventDefault();
    review.disabled = true;
    try {
      const result = await api("/api/order/prepare", {
        method: "POST", body: JSON.stringify({shipping_address: address.value})
      });
      state.cart = result.cart;
      state.confirmation = result.confirmation;
      state.confirmationDecision = null;
      state.order = null;
      renderCart();
      renderCheckout();
    } catch (error) { message("assistant", error.message); }
    finally { review.disabled = false; }
  });
  panel.append(form);
  renderCheckout();
}

function renderCheckout() {
  const panel = $("#checkoutPanel");
  panel.replaceChildren();
  panel.hidden = !(state.confirmation || state.order);
  if (state.order) {
    panel.className = "panel receipt";
    const title = document.createElement("h2");
    title.textContent = "Mock receipt";
    const number = document.createElement("p");
    number.textContent = state.order.order_number;
    const total = document.createElement("strong");
    total.textContent = `Total ${yen(state.order.total_jpy)}`;
    const note = document.createElement("p");
    note.textContent = "No money moved.";
    panel.append(title, number, total, note);
    return;
  }
  if (!state.confirmation) return;

  panel.className = "panel confirmation";
  const title = document.createElement("h2");
  title.textContent = "Confirm mock order";
  const address = document.createElement("p");
  address.textContent = `Ship to: ${state.confirmation.shipping_address}`;
  const expires = document.createElement("p");
  expires.textContent = `Expires: ${new Date(state.confirmation.expires_at).toLocaleString()}`;
  panel.append(title, address, expires);

  if (state.confirmationDecision) {
    const decided = document.createElement("strong");
    decided.textContent = `Decision: ${state.confirmationDecision}`;
    panel.append(decided);
    return;
  }

  const actions = document.createElement("div");
  actions.className = "decision-actions";
  for (const decision of ["reject", "approve"]) {
    const button = document.createElement("button");
    button.className = decision === "approve" ? "approve" : "danger";
    button.textContent = decision === "approve" ? "Approve" : "Reject";
    button.addEventListener("click", () => decide(decision));
    actions.append(button);
  }
  panel.append(actions);
}

async function decide(decision) {
  try {
    const result = await api("/api/order/decision", {
      method: "POST", body: JSON.stringify({decision})
    });
    state.confirmationDecision = decision;
    if (decision === "approve") {
      state.order = result.order;
      state.cart = {items: [], item_count: 0, total_jpy: 0};
      message("assistant", `Mock order ${result.order.order_number} confirmed. No money moved.`);
    } else {
      message("assistant", "Mock order rejected. Your cart was preserved.");
    }
    renderCart();
  } catch (error) { message("assistant", error.message); }
}

function handleToolResult(detail) {
  const result = detail.result || {};
  if (result.cart) state.cart = result.cart;
  if (result.confirmation) {
    state.confirmation = result.confirmation;
    state.confirmationDecision = null;
  }
  if (result.order) state.order = result.order;
  renderProducts(result);
  renderCart();
}

function handleSse(type, detail) {
  if (type === "assistant_delta") {
    if (!state.currentAssistant) state.currentAssistant = message("assistant", "");
    state.currentAssistant.textContent += detail.text || "";
    messages.scrollTop = messages.scrollHeight;
  } else if (type === "tool_started") {
    state.currentAssistant = null;
    message("tool", `Using MCP tool: ${detail.tool}`);
  } else if (type === "tool_result") {
    handleToolResult(detail);
  } else if (type === "error") {
    state.currentAssistant = null;
    message("assistant", detail.message || "Chat request failed.");
  } else if (type === "done") {
    state.currentAssistant = null;
  }
}

async function sendChat(value) {
  message("user", value);
  state.currentAssistant = null;
  setBusy(true);
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message: value})
    });
    if (!response.ok) {
      const body = await response.json();
      throw new Error(body.detail || "Chat request failed.");
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const {value: chunk, done} = await reader.read();
      if (done) break;
      buffer += decoder.decode(chunk, {stream: true});
      const frames = buffer.split("\n\n");
      buffer = frames.pop();
      for (const frame of frames) {
        let type = "message";
        let data = "{}";
        for (const line of frame.split("\n")) {
          if (line.startsWith("event:")) type = line.slice(6).trim();
          if (line.startsWith("data:")) data = line.slice(5).trim();
        }
        try { handleSse(type, JSON.parse(data)); }
        catch (_) { handleSse("error", {message: "Invalid event from chat server."}); }
      }
    }
  } catch (error) {
    message("assistant", error.message);
  } finally {
    state.currentAssistant = null;
    setBusy(false);
    $("#chatInput").focus();
  }
}

$("#loginForm").addEventListener("submit", async event => {
  event.preventDefault();
  const error = $("#loginError");
  error.hidden = true;
  try {
    const result = await api("/api/session/login", {
      method: "POST",
      body: JSON.stringify({name: $("#loginName").value, email: $("#loginEmail").value})
    });
    state.user = result.user;
    state.cart = result.cart;
    showAuthenticated(true);
    renderCart();
    messages.replaceChildren();
    message("assistant", "You are signed in to the local demo. What would you like to buy?");
    $("#chatInput").focus();
  } catch (reason) {
    error.textContent = reason.message;
    error.hidden = false;
  }
});

$("#chatForm").addEventListener("submit", event => {
  event.preventDefault();
  const input = $("#chatInput");
  const value = input.value.trim();
  if (!value || state.busy) return;
  input.value = "";
  sendChat(value);
});

$("#chatInput").addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    $("#chatForm").requestSubmit();
  }
});

$("#logoutButton").addEventListener("click", async () => {
  try { await api("/api/session", {method: "DELETE"}); } catch (_) {}
  Object.assign(state, {user:null, cart:null, confirmation:null, confirmationDecision:null, order:null});
  showAuthenticated(false);
});

(async () => {
  try {
    const health = await fetch("/healthz");
    const detail = await health.json();
    if (detail.model) $("#modelBadge").textContent = detail.model;
  } catch (_) {}
  try {
    const session = await api("/api/session");
    if (session.authenticated) {
      state.user = session.user;
      state.cart = session.cart;
      state.confirmation = session.confirmation;
      state.confirmationDecision = session.confirmation_decision;
      state.order = session.order;
      showAuthenticated(true);
      renderCart();
      message("assistant", "Welcome back. Your local cart is ready.");
    } else {
      showAuthenticated(false);
    }
  } catch (_) {
    showAuthenticated(false);
  }
})();
