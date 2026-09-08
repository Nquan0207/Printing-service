import { useEffect, useRef, useState } from "react";
import { Alert, Button, Group, Modal, Stack, Text, TextInput } from "@mantine/core";
import { AppBridge, PostMessageTransport } from "@modelcontextprotocol/ext-apps/app-bridge";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";

export type AppDescriptor = { id: string; server: string; tool: string; uri: string; input: Record<string, unknown> };
type Identity = { name: string; email: string };
export async function post(path: string, body: unknown) {
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || "Request failed");
  return result;
}
function report(result: Record<string, unknown>) {
  window.dispatchEvent(new CustomEvent("mcp-app-result", { detail: result }));
}
function wire(result: Record<string, unknown>, restored = false): CallToolResult {
  const raw = result._mcp_result as CallToolResult | undefined;
  const content = Object.fromEntries(Object.entries(result).filter(([key]) => !key.startsWith("_")));
  return { ...raw, content: raw?.content ?? [], structuredContent: { ...(raw?.structuredContent ?? content), ...content, _chat_host: { tokenFreeCheckout: true, restored } } };
}

export function IdentityForm({ onSubmit, onCancel }: { onSubmit: (identity: Identity) => Promise<void>; onCancel?: () => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return <form onSubmit={async event => {
    event.preventDefault(); setBusy(true); setError("");
    const identity = { name, email }; setName(""); setEmail("");
    try { await onSubmit(identity); } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }}><Stack gap="xs">
    <Text size="sm">Enter your registered administrator identity for this action.</Text>
    <TextInput label="Admin name" required value={name} autoComplete="off" onChange={e => setName(e.currentTarget.value)} />
    <TextInput label="Admin email" type="email" required value={email} autoComplete="off" onChange={e => setEmail(e.currentTarget.value)} />
    {error && <Alert color="red">{error}</Alert>}
    <Group><Button type="submit" loading={busy}>Run request</Button>{onCancel && <Button variant="default" onClick={onCancel}>Cancel</Button>}</Group>
  </Stack></form>;
}

export function OpsRequest({ id }: { id: string }) {
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  if (result?._mcp_app) return <MCPApp descriptor={result._mcp_app as AppDescriptor} result={result} />;
  if (result) return <Text>{String(result.message || "Request completed.")}</Text>;
  return <IdentityForm onSubmit={async identity => {
    const value = await post(`/api/apps/identity/${id}`, identity);
    if (value.error) throw new Error(value.error.message);
    setResult(value);
  }} />;
}

export function MCPApp({ descriptor, result, restored = false }: { descriptor: AppDescriptor; result: Record<string, unknown>; restored?: boolean }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [error, setError] = useState("");
  const [height, setHeight] = useState(600);
  const [identityRequest, setIdentityRequest] = useState(false);
  const [checkout, setCheckout] = useState<{ decision: string; summary: string } | null>(null);
  const identityResolver = useRef<((value: Identity | null) => void) | null>(null);
  const checkoutResolver = useRef<((value: boolean) => void) | null>(null);
  useEffect(() => {
    let disposed = false;
    const bridge = new AppBridge(null, { name: "Stockroom Ollama Chat", version: "1.0.0" }, { serverTools: {} });
    const timer = window.setTimeout(() => setError("The app did not initialize. Check the sandbox service and reload."), 20000);
    bridge.oninitialized = async () => {
      window.clearTimeout(timer);
      setError("");
      await bridge.sendToolInput({ arguments: descriptor.input });
      let seed = result;
      if (descriptor.server === "shop") {
        const session = await fetch("/api/session").then(r => r.json());
        seed = { ...result, user: session.user, cart: session.cart };
      }
      await bridge.sendToolResult(wire(seed, restored));
    };
    bridge.onsizechange = ({ height: next }) => { if (next) setHeight(Math.min(1200, Math.max(250, next))); };
    bridge.oncalltool = async ({ name, arguments: args = {} }) => {
      if (disposed) throw new Error("App closed");
      if (descriptor.server === "shop" && name === "mock_sign_in") {
        // The surrounding host already owns this identity; changing it needs
        // the normal logout/login flow, which also changes persisted history.
        const session = await fetch("/api/session").then(r => r.json());
        if (!session.authenticated) throw new Error("Sign in to the chat first.");
        if (args.email && String(args.email).trim() !== session.user.email) throw new Error("Log out of chat to switch accounts.");
        return wire({ user: session.user, cart: session.cart });
      }
      if (descriptor.server === "shop" && name === "place_order") {
        const decision = String(args.decision);
        if (!["approve", "reject"].includes(decision)) throw new Error("Invalid decision");
        const session = await fetch("/api/session").then(r => r.json());
        if (!session.confirmation) throw new Error("Prepare the order first.");
        const accepted = await new Promise<boolean>(resolve => {
          if (checkoutResolver.current) { resolve(false); return; }
          checkoutResolver.current = resolve;
          setCheckout({ decision, summary: `${session.cart?.item_count ?? 0} items · ¥${session.cart?.total_jpy ?? 0} · ${session.confirmation.shipping_address}` });
        });
        if (!accepted) throw new Error("Decision cancelled");
        const value = await post("/api/order/decision", { decision, review_id: session.confirmation.review_id });
        report(value);
        return wire(value);
      }
      let identity: Identity | null = null;
      if (descriptor.server === "ops") {
        identity = await new Promise<Identity | null>(resolve => {
          if (identityResolver.current) { resolve(null); return; }
          identityResolver.current = resolve; setIdentityRequest(true);
        });
        if (!identity) throw new Error("Admin request cancelled");
      }
      const value = await post(`/api/apps/${descriptor.id}/tools`, { name, arguments: args, identity });
      if (value.error) throw new Error(value.error.message);
      if (descriptor.server === "shop") report({ ...value, _tool: name });
      return wire(value);
    };
    void (async () => {
      try {
        const response = await fetch(`/api/apps/${descriptor.id}/resource`);
        const resource = await response.json();
        if (!response.ok) throw new Error(resource.detail);
        const html = resource.contents?.find((item: { text?: string }) => typeof item.text === "string")?.text;
        if (!html) throw new Error("The server returned no app HTML.");
        if (disposed || !frame.current?.contentWindow) return;
        bridge.onsandboxready = () => { void bridge.sendSandboxResourceReady({ html, sandbox: "allow-scripts" }); };
        await bridge.connect(new PostMessageTransport(frame.current.contentWindow, frame.current.contentWindow));
        const sandboxHost = location.hostname === "127.0.0.1" ? "localhost" : "127.0.0.1";
        const sandbox = new URL(import.meta.env.VITE_MCP_SANDBOX_ORIGIN || `${location.protocol}//${sandboxHost}:${location.port}`);
        if (sandbox.origin === location.origin) throw new Error("The app sandbox must use a separate origin.");
        frame.current.src = `${sandbox.origin}/sandbox/`;
      } catch (e) { if (!disposed) setError(String(e)); }
    })();
    return () => {
      disposed = true; window.clearTimeout(timer);
      identityResolver.current?.(null); identityResolver.current = null;
      checkoutResolver.current?.(false); checkoutResolver.current = null;
      void bridge.teardownResource({}).catch(() => {}).finally(() => bridge.close());
    };
  }, [descriptor.id]);
  return <Stack gap="xs">
    {error && <Alert color="red">{error}</Alert>}
    <iframe ref={frame} title={descriptor.tool} sandbox="allow-scripts allow-same-origin" referrerPolicy="origin" style={{ width: "100%", height, border: 0 }} />
    <Modal opened={identityRequest} onClose={() => { identityResolver.current?.(null); identityResolver.current = null; setIdentityRequest(false); }} title="Administrator identity" closeOnClickOutside={false}>
      {identityRequest && <IdentityForm onSubmit={async identity => { identityResolver.current?.(identity); identityResolver.current = null; setIdentityRequest(false); }} />}
    </Modal>
    <Modal opened={!!checkout} onClose={() => { checkoutResolver.current?.(false); checkoutResolver.current = null; setCheckout(null); }} title="Confirm mock checkout">
      <Text>{checkout?.summary}</Text>
      <Button mt="md" onClick={() => { checkoutResolver.current?.(true); checkoutResolver.current = null; setCheckout(null); }}>{checkout?.decision === "approve" ? "Approve mock order" : "Reject mock order"}</Button>
    </Modal>
  </Stack>;
}
