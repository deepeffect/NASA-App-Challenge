/** Sohbet durumu + SSE akışı. Olay tipleri: docs/API.md → "Sohbet (SSE)". */
import { useCallback, useRef, useState } from "react";

import type { EmergencyNotice, SSEMeta } from "../../api/client";
import { streamChat } from "../../api/sse";

export interface ToolActivity {
  id: string;
  name: string;
  status: "running" | "ok" | "error";
  durationMs?: number;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  tools: ToolActivity[];
  degraded?: boolean;
  ungrounded?: string[];
  error?: string;
}

export function useChatStream(astronautId: string, asOf: string | null) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [emergency, setEmergency] = useState<EmergencyNotice | null>(null);
  const [meta, setMeta] = useState<SSEMeta | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  /** Son (asistan) turunu güncelle. */
  const patchLast = useCallback((fn: (t: ChatTurn) => ChatTurn) => {
    setTurns((prev) => {
      if (!prev.length) return prev;
      const next = prev.slice();
      next[next.length - 1] = fn(next[next.length - 1]);
      return next;
    });
  }, []);

  const send = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content || streaming) return;
      const history = [...turns, { role: "user" as const, content, tools: [] }];
      setTurns([...history, { role: "assistant", content: "", tools: [] }]);
      setStreaming(true);
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      try {
        await streamChat(
          {
            astronaut_id: astronautId,
            as_of: asOf,
            messages: history.filter((t) => t.content).map((t) => ({ role: t.role, content: t.content })),
          },
          {
            onMeta: setMeta,
            onEmergency: setEmergency,
            onToken: ({ text: tk }) => patchLast((t) => ({ ...t, content: t.content + tk })),
            onThinking: ({ text: tk }) => patchLast((t) => ({ ...t, thinking: (t.thinking ?? "") + tk })),
            onToolCall: ({ id, name }) =>
              patchLast((t) => ({ ...t, tools: [...t.tools, { id, name, status: "running" }] })),
            onToolResult: ({ id, ok, duration_ms }) =>
              patchLast((t) => ({
                ...t,
                tools: t.tools.map((x) => (x.id === id ? { ...x, status: ok ? "ok" : "error", durationMs: duration_ms } : x)),
              })),
            onDone: (d) =>
              patchLast((t) => ({
                ...t,
                content: t.content || d.message,
                degraded: d.degraded,
                ungrounded: d.ungrounded_numbers,
              })),
            onError: (e) => patchLast((t) => ({ ...t, error: e.message })),
          },
          ctrl.signal,
        );
      } catch (err) {
        patchLast((t) => ({ ...t, error: err instanceof Error ? err.message : "Bağlantı hatası" }));
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [astronautId, asOf, turns, streaming, patchLast],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);
  const reset = useCallback(() => {
    abortRef.current?.abort();
    setTurns([]);
    setEmergency(null);
  }, []);

  return { turns, streaming, emergency, dismissEmergency: () => setEmergency(null), meta, send, stop, reset };
}
