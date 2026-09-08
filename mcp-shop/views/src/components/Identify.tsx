import { useState } from "react";
import { Alert, Button, Group, Paper, Stack, Text, TextInput, Title } from "@mantine/core";
import { callTool } from "../lib/mcp";

/**
 * Shown when a panel needs to know who the shopper is.
 *
 * Browsing and the cart are anonymous, so a guest reaching order history has
 * genuinely nothing to show -- the server answers `identity_required` rather
 * than an empty list, because "you have never ordered" and "I do not know who
 * you are" are different statements.
 */
export function Identify({
  title, hint, onSignedIn,
}: {
  title: string;
  hint: string;
  onSignedIn: () => void;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await callTool("mock_sign_in", { name: name.trim(), email: email.trim() });
      onSignedIn();
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Paper p="md" radius="md" maw={420}>
      <Stack gap="xs">
        <Title order={2} size="h5">{title}</Title>
        <Text size="xs" c="dimmed">{hint}</Text>
        <Group gap="xs" grow wrap="nowrap">
          <TextInput size="xs" placeholder="Name" value={name}
            onChange={(e) => setName(e.currentTarget.value)} />
          <TextInput size="xs" placeholder="Email" type="email" value={email}
            onChange={(e) => setEmail(e.currentTarget.value)}
            onKeyDown={(e) => e.key === "Enter" && email.trim() && submit()} />
        </Group>
        {error && <Alert color="red" variant="light">{error}</Alert>}
        <Group justify="flex-end">
          <Button size="xs" loading={busy} disabled={!email.trim()} onClick={submit}>
            Continue
          </Button>
        </Group>
      </Stack>
    </Paper>
  );
}
