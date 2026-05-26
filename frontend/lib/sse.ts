/**
 * POST + Server-Sent-Events stream reader.
 * Browsers' EventSource only supports GET; for our POST + JSON-body endpoints
 * we hand-roll fetch + ReadableStream parsing of "data: {...}\n\n" frames.
 */
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.API_URL ||
  "http://127.0.0.1:8000";

export interface ProgressEvent {
  type: "started" | "progress" | "result" | "done" | "error";
  done?: number;
  total?: number;
  matched?: number;
  current?: string;
  elapsed_ms?: number;
  universe?: string;
  pattern?: string;
  message?: string;
  // result events carry the full payload — caller can narrow with a generic
  [k: string]: unknown;
}

export interface StreamHandlers<TResult> {
  onStart?:    (e: ProgressEvent) => void;
  onProgress?: (e: ProgressEvent) => void;
  onResult?:   (result: TResult) => void;
  onDone?:     () => void;
  onError?:    (err: Error) => void;
  signal?:     AbortSignal;
}

export async function streamPost<TResult>(
  path: string,
  body: unknown,
  handlers: StreamHandlers<TResult>,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "text/event-stream" },
      body: JSON.stringify(body),
      signal: handlers.signal,
    });
  } catch (e) {
    handlers.onError?.(new Error(`Network error: ${(e as Error).message}`));
    return;
  }

  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    handlers.onError?.(new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`));
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let resultSeen = false;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const frames = buf.split("\n\n");
      buf = frames.pop() ?? "";
      for (const frame of frames) {
        const line = frame.trim();
        if (!line || !line.startsWith("data:")) continue;
        const payload = line.replace(/^data:\s*/, "");
        if (!payload) continue;
        let evt: ProgressEvent;
        try { evt = JSON.parse(payload); } catch { continue; }
        switch (evt.type) {
          case "started":
            handlers.onStart?.(evt); break;
          case "progress":
            handlers.onProgress?.(evt); break;
          case "result":
            resultSeen = true;
            handlers.onResult?.(evt as unknown as TResult); break;
          case "done":
            handlers.onDone?.(); break;
          case "error":
            handlers.onError?.(new Error(String(evt.message ?? "stream error"))); break;
        }
      }
    }
    if (!resultSeen) handlers.onError?.(new Error("Stream ended without result"));
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    handlers.onError?.(e as Error);
  }
}
