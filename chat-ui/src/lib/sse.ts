// POST /api/chat answers with Server-Sent Events, and EventSource cannot POST
// -- so the frames are parsed off the fetch body stream by hand.

export type ChatEvent =
  | { type: "assistant_delta"; text?: string }
  | { type: "tool_started"; tool?: string }
  | { type: "tool_result"; tool?: string; result?: Record<string, unknown> }
  | { type: "error"; message?: string }
  | { type: "done" };

export async function streamChat(
  message: string,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    signal,
  });
  if (!response.ok || !response.body) {
    let detail = "Chat request failed.";
    try {
      detail = (await response.json())?.detail || detail;
    } catch {
      /* keep the default */
    }
    throw new Error(detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Frames are separated by a blank line; the trailing fragment stays in the
    // buffer until its terminator arrives.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      let type = "message";
      let data = "{}";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) type = line.slice(6).trim();
        if (line.startsWith("data:")) data = line.slice(5).trim();
      }
      try {
        onEvent({ type, ...JSON.parse(data) } as ChatEvent);
      } catch {
        onEvent({ type: "error", message: "Invalid event from chat server." });
      }
    }
  }
}
