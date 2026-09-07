import { useState } from "react";
import { Alert, Anchor, Button, Group, Paper, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";
import type { App } from "@modelcontextprotocol/ext-apps";
import { readResult } from "../lib/mcp";

/**
 * The sign-in form every admin View falls back to.
 *
 * The tools refuse to return data until the connection has been authenticated,
 * so a View's first payload is `auth_required` rather than a dashboard. This
 * renders in its place and, once the credentials check out, re-runs whatever
 * the View was asking for -- the panel fills in without another prompt.
 *
 * `admin_sign_in` is app-only, so the credentials go from this iframe to the
 * server through the host and are never offered to the model as a tool it
 * could call, or be talked into calling.
 */
export function isAuthRequired(payload: { error?: { code: string } } | null | undefined) {
  return payload?.error?.code === "auth_required";
}

export function AdminGate({ app, onSignedIn }: { app: App; onSignedIn: () => void }) {
  const [email, setEmail] = useState("");
  const [passcode, setPasscode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const out = readResult<{ status?: string }>(
        await app.callServerTool({
          name: "admin_sign_in",
          arguments: { email: email.trim(), passcode },
        }),
      );
      if (out.error) {
        setError(out.error.message);
        return;
      }
      // Never keep the passcode around once it has been spent.
      setPasscode("");
      onSignedIn();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Paper p="md" radius="md" maw={420}>
      <Stack gap="xs">
        <Title order={2} size="h5">Administrator sign-in</Title>
        <Text size="xs" c="dimmed">
          These operations are restricted. Sign in to view them.
        </Text>

        <TextInput
          size="xs"
          label="Email"
          placeholder="admin@stockroom.local"
          value={email}
          onChange={(e) => setEmail(e.currentTarget.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        <PasswordInput
          size="xs"
          label="Passcode"
          value={passcode}
          onChange={(e) => setPasscode(e.currentTarget.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />

        {error && <Alert color="red" variant="light">{error}</Alert>}

        <Group justify="flex-end">
          <Button size="xs" loading={busy} disabled={!email.trim() || !passcode} onClick={submit}>
            Sign in
          </Button>
        </Group>
      </Stack>
    </Paper>
  );
}


/** The payload a View falls back to after signing out, so the gate re-renders. */
export const AUTH_REQUIRED = {
  error: {
    code: "auth_required",
    message: "Sign in with an administrator email and passcode to view this.",
  },
} as const;

/**
 * Who is signed in, and the way out.
 *
 * The grant belongs to the connection rather than to one panel, so signing out
 * here ends it for every ops View in the conversation -- which is the point:
 * leaving an admin session open because no panel offered a way to close it is
 * how a shared screen leaks an order book.
 */
export function AdminSession({
  app, admin, onSignedOut,
}: {
  app: App;
  admin?: { email: string; name?: string } | null;
  onSignedOut: () => void;
}) {
  const [busy, setBusy] = useState(false);
  if (!admin) return null;

  const signOut = async () => {
    setBusy(true);
    try {
      await app.callServerTool({ name: "admin_sign_out", arguments: {} });
      onSignedOut();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Group gap={6} wrap="nowrap">
      <Text size="xs" c="dimmed">{admin.email}</Text>
      <Anchor component="button" type="button" size="xs" disabled={busy} onClick={signOut}>
        Sign out
      </Anchor>
    </Group>
  );
}
