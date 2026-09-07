import { lazy, Suspense, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import {
  ActionIcon,
  AppShell,
  Badge,
  Button,
  Center,
  Group,
  Loader,
  Text,
  Tooltip,
  useComputedColorScheme,
  useMantineColorScheme,
} from "@mantine/core";
import { api } from "./lib/api";
import { useSession } from "./lib/session";
import Login from "./pages/Login";
import Shop from "./pages/Shop";
import Orders from "./pages/Orders";
// Only admins ever load the dashboard, and it drags in recharts +
// @mantine/charts. Splitting it keeps that weight off the shop.
const Admin = lazy(() => import("./pages/Admin"));
import NotFound from "./pages/NotFound";

function ColorSchemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  const computed = useComputedColorScheme("light", { getInitialValueInEffect: true });
  return (
    <Tooltip label={computed === "dark" ? "Light mode" : "Dark mode"}>
      <ActionIcon
        variant="default"
        size="lg"
        onClick={() => setColorScheme(computed === "dark" ? "light" : "dark")}
        aria-label="Toggle color scheme"
      >
        {computed === "dark" ? "☀" : "☾"}
      </ActionIcon>
    </Tooltip>
  );
}

export default function App() {
  const { user, login, logout } = useSession();
  const [shopEnabled, setShopEnabled] = useState<boolean | null>(null);
  const location = useLocation();

  useEffect(() => {
    api.config().then((c) => setShopEnabled(c.shop_enabled)).catch(() => setShopEnabled(false));
  }, []);

  // Wait for the server's answer before routing: rendering the shop then
  // yanking it away once config arrives is worse than a brief spinner.
  if (shopEnabled === null) {
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    );
  }

  if (!user) return <Login onLogin={login} shopEnabled={shopEnabled} />;

  const navLink = (to: string, label: string) => {
    const active = location.pathname.startsWith(to);
    return (
      <Button
        key={to}
        component={Link}
        to={to}
        variant={active ? "light" : "subtle"}
        color={active ? "raksul" : "gray"}
        size="compact-md"
      >
        {label}
      </Button>
    );
  };

  return (
    <AppShell header={{ height: 60 }} padding="lg">
      <AppShell.Header>
        <Group h="100%" px="lg" gap="lg" wrap="nowrap">
          <Text component={Link} to="/" fw={800} size="lg" style={{ whiteSpace: "nowrap" }}>
            RAKSUL{" "}
            <Text span c="raksul" fw={500}>
              Stockroom
            </Text>
          </Text>

          <Group gap={4} style={{ flex: 1 }}>
            {shopEnabled && navLink("/shop", "Shop")}
            {shopEnabled && navLink("/orders", "Orders")}
            {user.is_admin && navLink("/admin", "Dashboard")}
          </Group>

          <Group gap="xs" wrap="nowrap">
            <Text size="sm" fw={500}>
              {user.name}
            </Text>
            {user.is_admin && (
              <Badge size="sm" variant="light" color="raksul">
                admin
              </Badge>
            )}
            <ColorSchemeToggle />
            <Button variant="default" size="compact-md" onClick={logout}>
              Sign out
            </Button>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Main>
        <Routes>
          {/* Landing route is role-aware: admins go straight to the
              dashboard, customers to the shop. Both can still navigate to the
              other by URL or the header. */}
          <Route
            path="/"
            element={<Navigate to={user.is_admin ? "/admin" : "/shop"} replace />}
          />
          {/* The shop toggle is server-side. With it off a signed-in user
              lands on Page not found; admins keep the dashboard. */}
          <Route path="/shop" element={shopEnabled ? <Shop /> : <NotFound />} />
          <Route path="/orders" element={shopEnabled ? <Orders /> : <NotFound />} />
          <Route
            path="/admin"
            element={
              user.is_admin ? (
                <Suspense
                  fallback={
                    <Center py="xl">
                      <Loader />
                    </Center>
                  }
                >
                  <Admin />
                </Suspense>
              ) : (
                <Navigate to="/" replace />
              )
            }
          />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </AppShell.Main>
    </AppShell>
  );
}
