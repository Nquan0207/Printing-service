import { useEffect, useState } from "react";
import { Group, Image, Table, Text } from "@mantine/core";
import { AUTH_REQUIRED, AdminGate, AdminSession, isAuthRequired, needsPasscode } from "../components/AdminGate";
import { ErrorPanel, Shell } from "../components/Shell";
import { createApp, readResult } from "../lib/mcp";
import { yen } from "../lib/format";

type Size = { size_name: string; price_adjustment_jpy: number; unit_price_jpy: number };
type Product = {
  id: number; name: string; brand: string | null; description: string | null;
  base_price_jpy: number; category: { name: string }; sizes: Size[]; images: string[];
  /** Present when the name matched more than one product. Offered rather than
   *  silently resolved: picking one row out of eight is how you show the
   *  wrong product. */
  other_matches?: { id: number; name: string }[];
  admin?: { email: string; name?: string } | null;
};

const app = createApp("Product");

export default function Product() {
  const [p, setP] = useState<(Product & { error?: { code: string; message: string } }) | null>(null);

  useEffect(() => {
    app.ontoolresult = (r: unknown) => setP(readResult<Product>(r));
    app.connect();
  }, []);

  if (!p) return <Shell title="Product" sub="Loading…">{null}</Shell>;
  if (p.error)
    return (
      <Shell title="Product" sub="">
        {isAuthRequired(p)
          // The product View has no fetch of its own: the model opened it, so
          // signing in here just clears the gate and asks the user to re-run.
          ? <AdminGate app={app} onSignedIn={() => setP(null)} passcodeRequired={needsPasscode(p)} />
          : <ErrorPanel error={p.error} />}
      </Shell>
    );
  if (!p.id) return <Shell title="Product" sub=""><Text size="sm" c="dimmed">No product returned.</Text></Shell>;

  return (
    <Shell
      title="Product"
      right={<AdminSession app={app} admin={p.admin} onSignedOut={() => setP(AUTH_REQUIRED)} />}
      sub={`#${p.id} · ${p.category?.name ?? ""}${p.brand ? ` · ${p.brand}` : ""}`}
    >
      {/* Images are absolute URLs at the Go service; the View's CSP names that
          origin, otherwise the sandbox would block them. */}
      {p.images.length ? (
        <Group gap="xs">
          {p.images.map((src) => (
            <Image key={src} src={src} alt="" w={120} h={120} fit="contain" radius="sm"
              style={{ border: "1px solid var(--mantine-color-default-border)" }} />
          ))}
        </Group>
      ) : (
        <Text size="sm" c="dimmed">No images.</Text>
      )}

      <div>
        <Text fw={700}>{p.name}</Text>
        {p.description && <Text size="sm" c="dimmed">{p.description}</Text>}
      </div>

      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Size</Table.Th>
            <Table.Th ta="right">Adjustment</Table.Th>
            <Table.Th ta="right">Unit price</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {p.sizes.map((s) => (
            <Table.Tr key={s.size_name}>
              <Table.Td>{s.size_name}</Table.Td>
              <Table.Td ta="right" c="dimmed">
                {s.price_adjustment_jpy >= 0 ? "+" : ""}{yen(s.price_adjustment_jpy)}
              </Table.Td>
              <Table.Td ta="right"><b>{yen(s.unit_price_jpy)}</b></Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>

      <Text size="xs" c="dimmed">
        Base {yen(p.base_price_jpy)} · unit price = base + adjustment
      </Text>

      {p.other_matches?.length ? (
        <Text size="sm" c="dimmed">
          Also matched: {p.other_matches.map((m) => `#${m.id} ${m.name}`).join(" · ")}
        </Text>
      ) : null}
    </Shell>
  );
}
