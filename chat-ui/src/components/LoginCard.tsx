import { useState } from "react";
import { Alert, Button, Paper, Stack, Text, TextInput, Title } from "@mantine/core";

type Props = { onSignIn: (name: string, email: string) => Promise<void> };

export function LoginCard({ onSignIn }: Props) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await onSignIn(name.trim(), email.trim());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Paper p="xl" radius="lg" maw={520} mx="auto" mt="10vh">
      <form onSubmit={submit}>
        <Stack gap="md">
          <div>
            <Text size="xs" fw={800} c="raksul.6" style={{ letterSpacing: "0.12em" }}>
              DEMO SIGN-IN
            </Text>
            <Title order={2} mt={4}>
              Choose your shopping identity
            </Title>
          </div>
          <Text c="dimmed" size="sm">
            No password is used or verified. Your cart, mock orders and chat history are
            stored in the local Stockroom database.
          </Text>
          <TextInput
            label="Name"
            placeholder="Quan"
            maxLength={100}
            value={name}
            onChange={(event) => setName(event.currentTarget.value)}
          />
          <TextInput
            label="Email"
            type="email"
            required
            placeholder="quan@example.com"
            maxLength={320}
            value={email}
            onChange={(event) => setEmail(event.currentTarget.value)}
          />
          {error && (
            <Alert color="red" variant="light">
              {error}
            </Alert>
          )}
          <Button type="submit" loading={busy} fullWidth>
            Start chatting
          </Button>
        </Stack>
      </form>
    </Paper>
  );
}
