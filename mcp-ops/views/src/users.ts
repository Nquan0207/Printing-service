import { boot, esc, readResult, renderError, table, yen } from "./ui";

type User = {
  id: number; name: string; email: string; is_admin: boolean;
  cart_lines: number; orders: number; spent_jpy: number;
};
type Payload = { users?: User[]; total?: number };

const out = document.getElementById("out")!;
const sub = document.getElementById("sub")!;
const app = boot("Users");

function render(data: Payload & { error?: { code: string; message: string } }) {
  if (data.error) return renderError(out, data.error);
  const users = data.users ?? [];
  sub.textContent = `${users.length} account${users.length === 1 ? "" : "s"}`;
  const rows = users.map((u) => `<tr>
    <td class="muted mono">${u.id}</td>
    <td>${esc(u.name)}${u.is_admin ? ' <span class="pill off">admin</span>' : ""}</td>
    <td class="muted">${esc(u.email)}</td>
    <td class="num">${u.cart_lines}</td>
    <td class="num">${u.orders}</td>
    <td class="num">${yen(u.spent_jpy)}</td>
  </tr>`);
  out.innerHTML = table(
    [{ label: "ID" }, { label: "Name" }, { label: "Email" },
     { label: "Cart", num: true }, { label: "Orders", num: true }, { label: "Spent", num: true }],
    rows,
  );
}

app.ontoolresult = (r) => render(readResult<Payload>(r));
app.connect();
