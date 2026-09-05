import { useState, type FormEvent } from "react";
import {
  Alert,
  Button,
  Center,
  Chip,
  Group,
  Paper,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import type { User } from "../lib/api";

type Props = {
  onLogin: (email: string, name?: string) => Promise<User>;
  shopEnabled: boolean;
};

const SUGGESTED = ["alice@stockroom.local", "bob@stockroom.local", "admin@stockroom.local"];

export default function Login({ onLogin, shopEnabled }: Props) {
  const [email, setEmail] = useState("alice@stockroom.local");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onLogin(email.trim(), name.trim() || undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Center mih="100vh" p="md">
      <Paper component="form" onSubmit={submit} p="xl" radius="lg" w="100%" maw={420} shadow="sm">
        <Stack gap="md">
          <div>
            <Title order={2}>
              RAKSUL{" "}
              <Text span c="raksul" fw={500} inherit>
                Stockroom
              </Text>
            </Title>
            <Text c="dimmed" size="sm" mt={4}>
              Enter an email to continue. Unknown addresses create a new account.
            </Text>
          </div>

          <TextInput
            label="Email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.currentTarget.value)}
            placeholder="you@example.com"
          />
          <TextInput
            label="Name"
            description="Used only when creating a new account"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            placeholder="Optional"
          />

          <Button type="submit" loading={busy} fullWidth>
            Continue
          </Button>

          {error && (
            <Alert color="red" variant="light">
              {error}
            </Alert>
          )}

          <Group gap={6}>
            {SUGGESTED.map((s) => (
              <Chip key={s} size="xs" checked={email === s} onClick={() => setEmail(s)}>
                {s.split("@")[0]}
              </Chip>
            ))}
          </Group>

          {!shopEnabled && (
            <Alert color="yellow" variant="light" title="Shop is disabled">
              <Text size="xs">
                <code>SHOP_ENABLED=false</code>. Signing in as a non-admin will show{" "}
                <b>Page not found</b>.
              </Text>
            </Alert>
          )}

          <Text size="xs" c="dimmed">
            No password is taken and nothing is verified — this is a demo user picker, not
            authentication.
          </Text>
        </Stack>
      </Paper>
    </Center>
  );
}
