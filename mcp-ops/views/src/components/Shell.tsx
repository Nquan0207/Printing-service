import { Alert, Badge, Box, Stack, Text, Title } from "@mantine/core";

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
  title, sub, bar, children,
}: {
  title: string;
  sub: string;
  bar?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Box p="md">
      <Title order={1}>{title}</Title>
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
