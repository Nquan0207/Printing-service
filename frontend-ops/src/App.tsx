import { useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api } from "./lib/api";
import { useSession } from "./lib/session";
import Login from "./pages/Login";
import Shop from "./pages/Shop";
import Orders from "./pages/Orders";
import Admin from "./pages/Admin";
import NotFound from "./pages/NotFound";

export default function App() {
  const { user, login, logout } = useSession();
  const [shopEnabled, setShopEnabled] = useState<boolean | null>(null);
  const location = useLocation();

  useEffect(() => {
    api.config().then((c) => setShopEnabled(c.shop_enabled)).catch(() => setShopEnabled(false));
  }, []);

  // Wait for the server's answer before routing: rendering the shop and then
  // yanking it away once config arrives is worse than a brief blank.
  if (shopEnabled === null) return <div className="boot">Loading…</div>;

  if (!user) return <Login onLogin={login} shopEnabled={shopEnabled} />;

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          RAKSUL <span>Stockroom</span>
        </Link>
        <nav>
          {shopEnabled && <Link to="/" className={location.pathname === "/" ? "on" : ""}>Shop</Link>}
          {shopEnabled && (
            <Link to="/orders" className={location.pathname === "/orders" ? "on" : ""}>Orders</Link>
          )}
          {user.is_admin && (
            <Link to="/admin" className={location.pathname.startsWith("/admin") ? "on" : ""}>
              Dashboard
            </Link>
          )}
        </nav>
        <div className="who">
          <span className="name">
            {user.name}
            {user.is_admin && <em className="badge">admin</em>}
          </span>
          <button onClick={logout}>Sign out</button>
        </div>
      </header>

      <main>
        <Routes>
          {/* The shop toggle is server-side. With it off, a signed-in user
              lands on Page not found; admins keep the dashboard. */}
          <Route path="/" element={shopEnabled ? <Shop /> : <NotFound />} />
          <Route path="/orders" element={shopEnabled ? <Orders /> : <NotFound />} />
          <Route
            path="/admin"
            element={user.is_admin ? <Admin /> : <Navigate to="/" replace />}
          />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  );
}
