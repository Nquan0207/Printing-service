import { Alert, Badge, Box, Group, Stack, Text, Title } from "@mantine/core";

/** A blank iframe reads as a host bug, so failures always render. */
export function ErrorPanel({ error }: { error: { code: string; message: string } }) {
  return (
    <Alert color="red" variant="light" title={error.code}>
      {error.message}
    </Alert>
  );
}

/** Every View is a title, a one-line summary, an optional control bar, then content. */
export function Shell({
  title, sub, bar, right, children,
}: {
  title: string;
  sub: string;
  bar?: React.ReactNode;
  /** Top-right slot -- the signed-in admin and their way out. */
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Box p="md">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Title order={1}>{title}</Title>
        {right}
      </Group>
      <Text size="xs" c="dimmed" mb="sm">{sub}</Text>
      {bar && <Box mb="sm">{bar}</Box>}
      <Stack gap="sm">{children}</Stack>
    </Box>
  );
}

const PILL_COLOR: Record<string, string> = {
  confirmed: "teal",
  cancelled: "raksul",
  pending: "yellow",
};

export function StatusPill({ status }: { status: string }) {
  return (
    <Badge size="sm" variant="light" tt="none" color={PILL_COLOR[status] ?? "gray"}>
      {status}
    </Badge>
  );
}
