import { useEffect, useRef, useState } from "react";
import { Badge, Button, Group, Image, Paper, Table, Text, TextInput, Title } from "@mantine/core";
import { AdminGate, isAuthRequired } from "../components/AdminGate";
import { ErrorPanel, Shell } from "../components/Shell";
import { createApp, readResult } from "../lib/mcp";
import { yen } from "../lib/format";

type Size = { size_name: string; unit_price_jpy: number };
type Product = {
  id: number; name: string; brand: string | null; base_price_jpy: number;
  description?: string | null; sizes: Size[]; images: string[];
};
type Group_ = { category: { slug: string; name: string }; count: number; products: Product[] };
type Payload = {
  groups?: Group_[];
  count?: number;
  selected_categories?: string[];
  unmatched_categories?: string[];
};

const app = createApp("Catalog");

function Detail({ p }: { p: Product }) {
  return (
    <Table.Tr>
      <Table.Td colSpan={5} bg="var(--mantine-color-default-hover)">
        {p.images.length ? (
          <Group gap="xs" mb="xs">
            {p.images.map((src) => (
              <Image key={src} src={src} alt="" w={96} h={96} fit="contain" radius="sm"
                style={{ border: "1px solid var(--mantine-color-default-border)" }} />
            ))}
          </Group>
        ) : (
          <Text size="sm" c="dimmed">No images.</Text>
        )}
        {p.description && <Text size="sm" c="dimmed" mb="xs">{p.description}</Text>}
        <Table maw={260}>
          <Table.Tbody>
            {p.sizes.map((s) => (
              <Table.Tr key={s.size_name}>
                <Table.Td>{s.size_name}</Table.Td>
                <Table.Td ta="right"><b>{yen(s.unit_price_jpy)}</b></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.Td>
    </Table.Tr>
  );
}

export default function Catalog() {
  const [data, setData] = useState<(Payload & { error?: { code: string; message: string } }) | null>(null);
  /** Slugs currently selected. Empty means "all categories". */
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  /** Rows expanded in place. The payload already carries every product's
   *  description, sizes and images, so drilling in needs no extra tool call. */
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  /** Previous selections, newest last -- what "←" walks back through. This is
   *  why the chip row stays narrow: the way back out of "All" is one button,
   *  not a list of every category you are not looking at. */
  const history = useRef<string[][]>([]);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    app.ontoolresult = (r: unknown) => {
      // A fresh result from the model is a new question; the old trail belongs
      // to the previous one. View-driven refetches keep theirs.
      history.current = [];
      const payload = readResult<Payload>(r);
      setData(payload);
      setSelected(new Set(payload.selected_categories ?? []));
    };
    app.connect();
  }, []);

  async function refetch(slugs: Set<string>, q: string) {
    setSelected(slugs);
    setLoading(true);
    try {
      const args: Record<string, unknown> = {};
      if (slugs.size) args.categories = [...slugs];
      if (q) args.q = q;
      const payload = readResult<Payload>(await app.callServerTool({ name: "list_products", arguments: args }));
      setData(payload);
      setSelected(new Set(payload.selected_categories ?? []));
    } finally {
      setLoading(false);
    }
  }

  function pick(slug: string) {
    window.clearTimeout(timer.current);
    // Every button changes the filter, so record what it is changing from.
    history.current.push([...selected]);
    const next = new Set(selected);
    if (slug === "") next.clear();
    else if (next.has(slug)) next.delete(slug);
    else next.add(slug);
    refetch(next, query);
  }

  function back() {
    window.clearTimeout(timer.current);
    refetch(new Set(history.current.pop() ?? []), query);
  }

  function search(value: string) {
    setQuery(value);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => refetch(selected, value.trim()), 300);
  }

  function toggleRow(id: number) {
    setExpanded((current) => {
      const next = new Set(current);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  if (!data) return <Shell title="Catalog" sub="Loading…">{null}</Shell>;
  if (data.error)
    return (
      <Shell title="Catalog" sub="">
        {isAuthRequired(data)
          ? <AdminGate app={app} onSignedIn={() => refetch(selected, query)} />
          : <ErrorPanel error={data.error} />}
      </Shell>
    );

  const groups = data.groups ?? [];
  const shown = selected.size
    ? `${groups.length} ${groups.length === 1 ? "category" : "categories"}`
    : "all categories";
  let sub = `${data.count ?? 0} products · ${shown}`;
  if (data.unmatched_categories?.length) {
    sub += ` · no match for: ${data.unmatched_categories.join(", ")}`;
  }

  // Chips are the categories on screen, nothing more: ask for two, see two.
  // Widening to every category is what "All" is for, and "←" is the way back.
  const bar = (
    <Group gap={6}>
      <TextInput size="xs" w={190} placeholder="Search products…" value={query}
        onChange={(e) => search(e.currentTarget.value)} />
      {history.current.length > 0 && (
        <Button size="compact-xs" variant="default" title="Back to the previous categories"
          onClick={back}>←</Button>
      )}
      <Button size="compact-xs" title="Every category"
        variant={selected.size === 0 ? "light" : "default"}
        color={selected.size === 0 ? "raksul" : "gray"} onClick={() => pick("")}>All</Button>
      {groups.map((g) => {
        const on = selected.has(g.category.slug);
        return (
          <Button key={g.category.slug} size="compact-xs" tt="none" title={g.category.slug}
            variant={on ? "light" : "default"} color={on ? "raksul" : "gray"}
            onClick={() => pick(g.category.slug)}>
            {g.category.name} <Text span c="dimmed" ml={4}>{g.count}</Text>
          </Button>
        );
      })}
    </Group>
  );

  return (
    <Shell title="Catalog" sub={loading ? "Loading…" : sub} bar={bar}>
      {groups.length === 0 ? (
        <Text size="sm" c="dimmed">No products match.</Text>
      ) : (
        groups.map((g) => (
          <Paper key={g.category.slug} p="sm" radius="md">
            <Group gap={7} mb={6}>
              <Title order={2} size="12px">{g.category.name}</Title>
              <Badge size="sm" variant="light" color="gray">{g.count}</Badge>
            </Group>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>ID</Table.Th><Table.Th /><Table.Th>Product</Table.Th>
                  <Table.Th ta="right">Base</Table.Th><Table.Th>Sizes</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {g.products.map((p) => {
                  const open = expanded.has(p.id);
                  return [
                    <Table.Tr key={p.id} style={{ cursor: "pointer" }}
                      title="Click for photos and description" onClick={() => toggleRow(p.id)}>
                      <Table.Td c="dimmed" ff="monospace" fz="xs">{open ? "▾" : "▸"} {p.id}</Table.Td>
                      <Table.Td>
                        {p.images[0] && (
                          <Image src={p.images[0]} alt="" w={32} h={32} fit="contain" radius={4} />
                        )}
                      </Table.Td>
                      <Table.Td>
                        {p.name}
                        {p.brand && <Text size="xs" c="dimmed">{p.brand}</Text>}
                      </Table.Td>
                      <Table.Td ta="right">{yen(p.base_price_jpy)}</Table.Td>
                      {/* Sizes arrive ordered by price adjustment, so S/M/L reads correctly. */}
                      <Table.Td c="dimmed">
                        {p.sizes.map((s) => `${s.size_name} ${yen(s.unit_price_jpy)}`).join(" · ")}
                      </Table.Td>
                    </Table.Tr>,
                    open ? <Detail key={`${p.id}-d`} p={p} /> : null,
                  ];
                })}
              </Table.Tbody>
            </Table>
          </Paper>
        ))
      )}
    </Shell>
  );
}
