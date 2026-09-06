STOREFRONT_URI = "ui://widget/raksul-stockroom-v3.html"

STOREFRONT_HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    :root {
      color-scheme: light dark;
      --bg:#fff; --panel:#f6f6f3; --text:#191918; --muted:#6b6b65;
      --line:#dddcd6; --accent:#e54824; --ok:#177447; --bad:#b42318;
    }
    @media(prefers-color-scheme:dark){
      :root{--bg:#1d1d1b;--panel:#292927;--text:#f4f3ee;--muted:#aaa9a2;--line:#45453f;--accent:#ff7654;--ok:#52b788;--bad:#ff7b72}
    }
    *{box-sizing:border-box}
    body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,sans-serif}
    .shell{max-width:1120px;margin:auto;padding:14px}
    header{display:flex;justify-content:space-between;align-items:center}
    h1,h2,h3{margin:0}
    .badge{color:var(--accent);font-weight:800}
    .notice,.panel,.status{background:var(--panel);border-radius:10px;padding:11px;margin:12px 0}
    .muted{color:var(--muted)}
    form,.row{display:flex;gap:8px}
    .login form{display:grid;grid-template-columns:1fr 1fr auto;margin-top:10px}
    input,select,button{font:inherit;color:var(--text);background:var(--bg);border:1px solid var(--line);border-radius:9px;padding:9px;min-width:0}
    button{cursor:pointer;font-weight:700}
    .primary{background:var(--accent);border-color:var(--accent);color:#fff}
    .approve{background:var(--ok);border-color:var(--ok);color:#fff}
    .reject{color:var(--bad)}
    button:disabled{opacity:.45}
    .search input{flex:1}
    .layout{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:14px}
    .products{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px}
    .card,.cart{border:1px solid var(--line);border-radius:12px;overflow:hidden}
    .media{height:145px;display:grid;place-items:center;background:var(--panel);color:var(--muted)}
    .media img{width:100%;height:145px;object-fit:contain}
    .pad,.cart{padding:10px}
    .name{font-weight:750;min-height:42px}
    .price{font-size:16px;font-weight:800;margin:5px 0}
    .choices,.actions{display:grid;gap:7px;margin:9px 0}
    .choices label{display:grid}
    .cart{position:sticky;top:8px;align-self:start}
    .line{border-top:1px solid var(--line);padding:9px 0}
    .line span{flex:1}
    .total{display:flex;justify-content:space-between;border-top:1px solid var(--line);padding-top:9px;font-weight:800}
    .receipt{border:2px solid var(--ok)}
    .bridge-error{border:1px solid var(--bad);color:var(--bad)}
    [hidden]{display:none!important}
    @media(max-width:720px){.login form,.layout{grid-template-columns:1fr}.cart{position:static}}
  </style>
</head>
<body>
<main class="shell">
  <header><h1>RAKSUL Stockroom</h1><span class="badge">DATABASE MOCK</span></header>
  <div class="notice">Catalog, sizes, cart, and orders come from the Stockroom backend through MCP tools. No supplier website opens and no real payment occurs.</div>
  <div class="status bridge-error" id="bridgeError" hidden></div>

  <section class="panel login" id="login">
    <h2>Select demo user</h2>
    <p class="muted">This creates or selects a database user without a password.</p>
    <form id="loginForm">
      <input id="name" placeholder="Name">
      <input id="email" required type="email" placeholder="Email">
      <button class="primary">Continue</button>
    </form>
  </section>

  <section id="store" hidden>
    <div class="status" id="customer"></div>
    <form class="search" id="searchForm">
      <input id="query" placeholder="Search Stockroom products">
      <button class="primary">Search</button>
    </form>
    <p id="message" class="muted"></p>
    <div class="layout">
      <section class="products" id="products"></section>
      <aside class="cart" id="cart"></aside>
    </div>
  </section>
</main>

<script>
const MCP_APPS_PROTOCOL_VERSION = "2026-01-26";
const APP_INFO = {name: "raksul-stockroom", version: "3.1.0"};

const S = {
  products: [], user: null, cart: null, confirmation: null, order: null,
  busy: false, hostContext: {}, toolInput: {}
};

const pending = new Map();
let nextId = 1;
let bridgeReady = Promise.resolve();
let resizeObserver = null;

function post(message) {
  window.parent.postMessage(message, "*");
}

function rpc(method, params = {}) {
  const id = nextId++;
  post({jsonrpc: "2.0", id, method, params});
  return new Promise((resolve, reject) => pending.set(id, {resolve, reject}));
}

function notify(method, params = {}) {
  post({jsonrpc: "2.0", method, params});
}

function reply(id, result = {}) {
  post({jsonrpc: "2.0", id, result});
}

function unwrap(value) {
  return value?.structuredContent ?? value?.structured_content ?? value ?? {};
}

function showBridgeError(error) {
  const el = document.getElementById("bridgeError");
  el.hidden = false;
  el.textContent = `MCP App bridge error: ${error?.message || error}`;
}

function startAutoResize() {
  if (resizeObserver || !window.ResizeObserver) return;
  let lastWidth = 0;
  let lastHeight = 0;
  const sendSize = () => {
    const root = document.documentElement;
    const body = document.body;
    const width = Math.ceil(Math.max(root.scrollWidth, body.scrollWidth));
    const height = Math.ceil(Math.max(root.scrollHeight, body.scrollHeight));
    if (width === lastWidth && height === lastHeight) return;
    lastWidth = width;
    lastHeight = height;
    notify("ui/notifications/size-changed", {width, height});
  };
  resizeObserver = new ResizeObserver(sendSize);
  resizeObserver.observe(document.documentElement);
  resizeObserver.observe(document.body);
  sendSize();
}

function stopAutoResize() {
  resizeObserver?.disconnect();
  resizeObserver = null;
}

window.addEventListener("message", (event) => {
  if (event.source !== window.parent) return;
  const message = event.data;
  if (!message || message.jsonrpc !== "2.0") return;

  if (message.id !== undefined && pending.has(message.id)) {
    const waiter = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) {
      waiter.reject(new Error(message.error.message || "MCP host request failed"));
    } else {
      waiter.resolve(message.result);
    }
    return;
  }

  switch (message.method) {
    case "ui/notifications/tool-result":
      seed(unwrap(message.params));
      break;
    case "ui/notifications/tool-input":
      S.toolInput = message.params?.arguments || {};
      break;
    case "ui/notifications/host-context-changed":
      S.hostContext = {...S.hostContext, ...(message.params || {})};
      break;
    case "ui/notifications/tool-cancelled":
      say(message.params?.reason || "Tool call was cancelled.", true);
      break;
    case "ui/resource-teardown":
      stopAutoResize();
      if (message.id !== undefined) reply(message.id, {});
      break;
  }
});

async function initializeStandardMcpApp() {
  // This is the part that was incorrect in the old widget:
  // - `appCapabilities` is required (not `capabilities`)
  // - `protocolVersion` is required
  // - the View must send `ui/notifications/initialized` after the response
  const initResult = await rpc("ui/initialize", {
    protocolVersion: MCP_APPS_PROTOCOL_VERSION,
    appInfo: APP_INFO,
    appCapabilities: {
      availableDisplayModes: ["inline", "fullscreen"]
    }
  });

  S.hostContext = initResult?.hostContext || {};
  notify("ui/notifications/initialized", {});
  startAutoResize();
  return initResult;
}

async function tool(name, args = {}) {
  S.busy = true;
  draw();
  try {
    let raw;
    if (window.openai?.callTool) {
      // ChatGPT Apps SDK compatibility path.
      raw = await window.openai.callTool(name, args);
    } else {
      // Claude / standard MCP Apps path.
      await bridgeReady;
      raw = await rpc("tools/call", {name, arguments: args});
    }

    const out = unwrap(raw);
    if (out.status === "error") {
      throw new Error(out.error?.message || "Tool failed");
    }
    return out;
  } finally {
    S.busy = false;
    draw();
  }
}

function seed(output) {
  if (!output || typeof output !== "object") return;
  if (output.groups) S.products = output.groups.flatMap(group => group.products || []);
  if (output.user) S.user = output.user;
  if (output.cart) S.cart = output.cart;
  if (output.confirmation) S.confirmation = output.confirmation;
  if (output.order) S.order = output.order;
  draw();
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
  }[c]));
}

function yen(value) {
  return Number.isInteger(value) ? `¥${value.toLocaleString()}` : "—";
}

function say(text, bad = false) {
  const el = document.getElementById("message");
  el.textContent = text;
  el.style.color = bad ? "var(--bad)" : "var(--muted)";
}

function safeImageUrl(value) {
  if (typeof value !== "string") return "";

  const allowed =
    /^https:\/\//i.test(value) ||
    /^http:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?\//i.test(value) ||
    /^data:image\//i.test(value);

  return allowed ? value : "";
}

function card(product) {
  const imageUrl = safeImageUrl(product.images?.[0]);
  const image = imageUrl
    ? `<div class="media"><img src="${esc(imageUrl)}" alt="" onerror="this.remove();this.parentElement.textContent='No image'"></div>`
    : `<div class="media">No image</div>`;

  const sizes = (product.sizes || []).map(size =>
    `<option value="${size.id}">${esc(size.size_name)} · ${yen(size.unit_price_jpy)}</option>`
  ).join("");

  return `<article class="card">${image}<div class="pad">
    <div class="name">${esc(product.name)}</div>
    <div class="muted">${esc(product.category?.name || product.brand || "")}</div>
    <div class="price">From ${yen(product.base_price_jpy)}</div>
    <div class="choices">
      <label>Size<select id="size-${product.id}"><option value="">Select size</option>${sizes}</select></label>
      <label>Quantity<input id="qty-${product.id}" type="number" min="1" value="1"></label>
    </div>
    <button class="primary" ${!sizes || S.busy ? "disabled" : ""} onclick="add(${product.id})">Quote and add</button>
  </div></article>`;
}

function cart() {
  const c = S.cart;
  if (!c) return "<h2>Cart</h2><p class=muted>Loading database cart…</p>";

  const lines = (c.items || []).map(item => `<div class="line">
    <strong>${esc(item.product_name)}</strong>
    <div class="muted">${esc(item.size_name)} · ${item.quantity}</div>
    <div class="row"><span>${yen(item.subtotal_jpy)}</span><button onclick="removeLine(${item.id})">Remove</button></div>
  </div>`).join("");

  let next = "";
  if (S.confirmation) {
    next = `<div class="status"><strong>Explicit mock confirmation</strong>
      <p>Address: ${esc(S.confirmation.shipping_address)}</p>
      <p>Total: ${yen(c.total_jpy)}</p>
      <div class="actions">
        <button class="approve" onclick="decide('approve')">Approve mock order</button>
        <button class="reject" onclick="decide('reject')">Reject mock order</button>
      </div>
    </div>`;
  } else if (S.order) {
    next = `<div class="status receipt"><strong>Mock receipt</strong>
      <p>${esc(S.order.order_number)}</p><p>Total ${yen(S.order.total_jpy)}</p><p>No money moved.</p>
    </div>`;
  }

  return `<h2>Cart · ${c.item_count || 0}</h2>
    ${lines || '<p class=muted>Empty cart.</p>'}
    <div class="total"><span>Total</span><span>${yen(c.total_jpy)}</span></div>
    <div class="actions">
      <input id="address" placeholder="Mock shipping address">
      <button class="primary" ${!c.items?.length || S.busy ? "disabled" : ""} onclick="prepare()">Review mock order</button>
    </div>${next}`;
}

function draw() {
  document.getElementById("login").hidden = !!S.user;
  document.getElementById("store").hidden = !S.user;
  if (!S.user) return;

  document.getElementById("customer").innerHTML =
    `Demo user <strong>${esc(S.user.name)}</strong> · ${esc(S.user.email)}`;
  document.getElementById("products").innerHTML =
    S.products.map(card).join("") || '<p class=muted>No products in the Stockroom database.</p>';
  document.getElementById("cart").innerHTML = cart();
}

document.getElementById("loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    let output = await tool("mock_sign_in", {
      name: document.getElementById("name").value,
      email: document.getElementById("email").value
    });
    S.user = output.user;
    output = await tool("get_cart");
    S.cart = output.cart;
    say("Database user and cart loaded.");
  } catch (error) {
    say(error.message, true);
  }
  draw();
});

document.getElementById("searchForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const output = await tool("search_products", {
      query: document.getElementById("query").value || null,
      limit: 30
    });
    S.products = (output.groups || []).flatMap(group => group.products || []);
    say(`${output.count || 0} product(s).`);
  } catch (error) {
    say(error.message, true);
  }
  draw();
});

async function add(id) {
  try {
    const size_id = Number(document.getElementById(`size-${id}`).value);
    const quantity = Number(document.getElementById(`qty-${id}`).value);
    if (!size_id) throw new Error("Select a size.");

    const quoteOutput = await tool("get_quote", {product_id: id, size_id, quantity});
    const notes = Array.isArray(quoteOutput.quote?.notes) ? quoteOutput.quote.notes.join(" ") : "";
    say(`${quoteOutput.quote.product_name}: ${yen(quoteOutput.quote.subtotal_jpy)}. ${notes}`.trim());

    const cartOutput = await tool("add_to_cart", {product_id: id, size_id, quantity});
    S.cart = cartOutput.cart;
    S.confirmation = null;
    S.order = null;
  } catch (error) {
    say(error.message, true);
  }
  draw();
}

async function removeLine(item_id) {
  try {
    const output = await tool("remove_cart_item", {item_id});
    S.cart = output.cart;
    S.confirmation = null;
  } catch (error) {
    say(error.message, true);
  }
  draw();
}

async function prepare() {
  try {
    const shipping_address = document.getElementById("address").value;
    const output = await tool("prepare_order", {shipping_address});
    S.cart = output.cart;
    S.confirmation = output.confirmation;
    S.order = null;
    say("Review and explicitly approve or reject.");
  } catch (error) {
    say(error.message, true);
  }
  draw();
}

async function decide(decision) {
  try {
    const output = await tool("place_order", {
      confirmation_token: S.confirmation.token,
      decision
    });
    S.confirmation = null;
    if (decision === "approve") {
      S.order = output.order;
      S.cart = {items: [], item_count: 0, total_jpy: 0};
      say("Mock order stored in the Stockroom database.");
    } else {
      say("Rejected. Database cart preserved.");
    }
  } catch (error) {
    say(error.message, true);
  }
  draw();
}

(async () => {
  // Install listeners before beginning initialization so the initial tool result is not missed.
  if (window.openai?.callTool) {
    if (window.openai?.toolOutput) seed(unwrap(window.openai.toolOutput));
    draw();
    return;
  }

  bridgeReady = initializeStandardMcpApp().catch(error => {
    console.error(error);
    showBridgeError(error);
    throw error;
  });

  try {
    await bridgeReady;
  } catch (_) {
    // Error is already visible in the widget.
  }
  draw();
})();
</script>
</body>
</html>'''
