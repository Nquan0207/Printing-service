/**
 * MCP Apps bridge for a View.
 *
 * The protocol itself is the official `App` client's job -- the ui/initialize
 * handshake, capability negotiation, JSON-RPC framing over postMessage,
 * auto-resize and teardown. This module adds only the two things every View
 * here needs on top: unwrapping a tool result, and the ChatGPT Apps SDK
 * fallback the server advertises via its openai/* meta.
 */
import { App } from "@modelcontextprotocol/ext-apps";

export const app = new App({ name: "raksul-stockroom", version: "3.1.0" });

/** A tool result arrives either structured or as a JSON text block. */
export function unwrap<T = any>(value: any): T {
  return (value?.structuredContent ?? value?.structured_content ?? value ?? {}) as T;
}

export async function callTool<T = any>(name: string, args: Record<string, any> = {}): Promise<T> {
  const openai = (window as any).openai;
  const raw = openai?.callTool
    ? await openai.callTool(name, args)
    : await app.callServerTool({ name, arguments: args });

  const out = unwrap<any>(raw);
  if (out?.status === "error") throw new Error(out.error?.message || "Tool failed");
  return out as T;
}

/** ChatGPT hands the first result over as a property, not a notification. */
export function initialToolOutput(): any | null {
  const openai = (window as any).openai;
  return openai?.callTool ? unwrap(openai.toolOutput) : null;
}

export const isOpenAIHost = () => Boolean((window as any).openai?.callTool);
