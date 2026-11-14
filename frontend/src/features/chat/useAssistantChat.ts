/**
 * Sohbet → asistan API'si (POST /chat {message} → answer + sources). Araç döngüsü ve sistem prompt'u
 * o API'nin içindedir. "daily report" mesajları GET /daily_report'a gider (rapor kartıyla aynı önbellek).
 * Acil belirti taraması LLM'den bağımsızdır: her mesaj aynı anda bizim backend'in kural tabanlı
 * /api/emergency/check ucuna da gönderilir ve banner cevabı beklemeden gösterilir.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";

import { api, type EmergencyNotice } from "../../api/client";
import { assistantApi, assistantKeys, type DailyReportResponse, type Sources } from "../assistant/api";

export interface AssistantTurn {
  role: "user" | "assistant";
  content: string;
  sources?: Sources;
  error?: string;
}

const REPORT_INTENT = /\bdaily\s+report\b/i;

export function useAssistantChat() {
  const qc = useQueryClient();
  const [turns, setTurns] = useState<AssistantTurn[]>([]);
  const [pending, setPending] = useState(false);
  const [emergency, setEmergency] = useState<EmergencyNotice | null>(null);
  const ctrlRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || ctrlRef.current) return;
      const ctrl = new AbortController();
      ctrlRef.current = ctrl;
      setTurns((t) => [...t, { role: "user", content: message }]);
      setPending(true);

      // Kural tabanlı acil tarama: asistan cevabını beklemez, asistan kapalıyken de çalışır
      api
        .emergencyCheck(message)
        .then((r) => {
          if (r.notice) setEmergency(r.notice);
        })
        .catch(() => undefined);

      try {
        let reply: AssistantTurn;
        if (REPORT_INTENT.test(message)) {
          const r = await qc.fetchQuery<DailyReportResponse>({
            queryKey: assistantKeys.report,
            queryFn: ({ signal }) => assistantApi.dailyReport(false, signal),
            staleTime: 10 * 60_000,
          });
          reply = { role: "assistant", content: r.report, sources: r.sources };
        } else {
          const r = await assistantApi.chat(message, ctrl.signal);
          const content = r.answer ?? r.report ?? "";
          reply = content
            ? { role: "assistant", content, sources: r.sources }
            : { role: "assistant", content: "", error: "The assistant returned an empty answer." };
        }
        if (!ctrl.signal.aborted) setTurns((t) => [...t, reply]);
      } catch (e) {
        if (!ctrl.signal.aborted) {
          setTurns((t) => [...t, { role: "assistant", content: "", error: e instanceof Error ? e.message : String(e) }]);
        }
      } finally {
        if (ctrlRef.current === ctrl) {
          ctrlRef.current = null;
          setPending(false);
        }
      }
    },
    [qc],
  );

  const stop = useCallback(() => {
    if (!ctrlRef.current) return;
    ctrlRef.current.abort();
    ctrlRef.current = null;
    setPending(false);
    setTurns((t) => [...t, { role: "assistant", content: "", error: "Stopped." }]);
  }, []);

  const reset = useCallback(() => {
    ctrlRef.current?.abort();
    ctrlRef.current = null;
    setPending(false);
    setTurns([]);
    setEmergency(null);
    assistantApi.reset().catch(() => undefined); // asistan tarafındaki sohbet geçmişi de sıfırlansın
  }, []);

  return { turns, pending, emergency, dismissEmergency: () => setEmergency(null), send, stop, reset };
}
