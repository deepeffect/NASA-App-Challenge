/**
 * POST + SSE sohbet akışı. Tarayıcının EventSource'u POST desteklemediği için
 * @microsoft/fetch-event-source kullanılır. Olay tipleri: docs/API.md → "Sohbet (SSE)".
 */
import { EventStreamContentType, fetchEventSource } from "@microsoft/fetch-event-source";

import {
  API_BASE,
  type ChatEventName,
  type ChatRequest,
  type EmergencyNotice,
  type SSEDone,
  type SSEError,
  type SSEMeta,
  type SSEThinking,
  type SSEToken,
  type SSEToolCall,
  type SSEToolResult,
} from "./client";

export interface ChatHandlers {
  onMeta?: (e: SSEMeta) => void;
  onToken?: (e: SSEToken) => void;
  onThinking?: (e: SSEThinking) => void;
  onToolCall?: (e: SSEToolCall) => void;
  onToolResult?: (e: SSEToolResult) => void;
  onEmergency?: (e: EmergencyNotice) => void;
  onDone?: (e: SSEDone) => void;
  onError?: (e: SSEError) => void;
}

class FatalStreamError extends Error {}

export async function streamChat(req: ChatRequest, handlers: ChatHandlers, signal?: AbortSignal): Promise<void> {
  await fetchEventSource(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: EventStreamContentType },
    body: JSON.stringify(req),
    signal,
    openWhenHidden: true,
    async onopen(res) {
      if (res.ok && res.headers.get("content-type")?.startsWith(EventStreamContentType)) return;
      let detail = `HTTP ${res.status}`;
      try {
        const j = await res.json();
        detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
      } catch {
        /* JSON değil */
      }
      throw new FatalStreamError(detail);
    },
    onmessage(ev) {
      if (!ev.event || !ev.data) return;
      const data = JSON.parse(ev.data);
      switch (ev.event as ChatEventName) {
        case "meta":
          handlers.onMeta?.(data);
          break;
        case "token":
          handlers.onToken?.(data);
          break;
        case "thinking":
          handlers.onThinking?.(data);
          break;
        case "tool_call":
          handlers.onToolCall?.(data);
          break;
        case "tool_result":
          handlers.onToolResult?.(data);
          break;
        case "emergency":
          handlers.onEmergency?.(data);
          break;
        case "done":
          handlers.onDone?.(data);
          break;
        case "error":
          handlers.onError?.(data);
          break;
      }
    },
    onerror(err) {
      // Varsayılan davranış otomatik yeniden denemedir; sohbet için istemiyoruz.
      throw err;
    },
  });
}
