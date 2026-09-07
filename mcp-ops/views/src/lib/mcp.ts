/**
 * MCP Apps bridge for a View.
 *
 * The protocol is the official `App` client's job: the ui/initialize
 * handshake, JSON-RPC framing over postMessage, auto-resize and teardown.
 * This module adds only result unwrapping on top.
 */
import { App } from "@modelcontextprotocol/ext-apps";

export type ToolError = { error?: { code: string; message: string } };

export function createApp(name: string) {
  return new App({ name, version: "0.1.0" });
}

/** Unwrap a tool result into its structured payload. */
export function readResult<T>(result: unknown): T & ToolError {
  const r = result as { structuredContent?: T; content?: { type: string; text?: string }[] };
  if (r?.structuredContent) return r.structuredContent as T & ToolError;
  const text = r?.content?.find((c) => c.type === "text")?.text;
  try {
    return (text ? JSON.parse(text) : {}) as T & ToolError;
  } catch {
    return { error: { code: "parse_error", message: text ?? "Unreadable tool result" } } as T & ToolError;
  }
}
