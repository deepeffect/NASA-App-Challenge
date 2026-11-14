/**
 * Sohbet paneli → asistan API'si (bkz. useAssistantChat). Cevaptaki [D1]/[K1] etiketleri kaynak rozetidir.
 * Acil belirti bandı bizim backend'in kural tabanlı taramasından gelir (LLM'den bağımsız).
 */
import { useEffect, useRef, useState, type FormEvent } from "react";

import { EmergencyBanner } from "../../components/ui/EmergencyBanner";
import { SendIcon, StopIcon } from "../../components/ui/icons";
import { Button, Card } from "../../components/ui/primitives";
import { AssistantDataTag, SourceList, SourceText, Waiting } from "../assistant";
import { useAssistantChat } from "./useAssistantChat";

const SUGGESTIONS = ["What is my daily report?", "How is my sleep?", "Why is my heart rate high?"];

export function ChatPanel() {
  const chat = useAssistantChat();
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [chat.turns, chat.pending]);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || chat.pending) return;
    void chat.send(input);
    setInput("");
  };

  return (
    <Card
      title="Health assistant"
      actions={
        <div className="flex items-center gap-2">
          <AssistantDataTag />
          {chat.turns.length > 0 && (
            <Button variant="ghost" onClick={chat.reset} className="text-sm">
              Clear
            </Button>
          )}
        </div>
      }
    >
      <div className="space-y-4">
        {chat.emergency && <EmergencyBanner notice={chat.emergency} onDismiss={chat.dismissEmergency} />}

        <div className="max-h-[28rem] space-y-3 overflow-y-auto pr-1" aria-live="polite">
          {chat.turns.length === 0 && !chat.pending && (
            <div className="space-y-2">
              <p className="text-slate-400">Ask about your health data. The assistant does not diagnose; it provides decision support.</p>
              <div className="flex flex-wrap gap-2">
                {SUGGESTIONS.map((s) => (
                  <Button key={s} variant="secondary" className="text-sm" onClick={() => void chat.send(s)}>
                    {s}
                  </Button>
                ))}
              </div>
            </div>
          )}
          {chat.turns.map((t, i) =>
            t.role === "user" ? (
              <div key={i} className="ml-8 whitespace-pre-wrap rounded-2xl bg-sky-900/40 px-4 py-2">
                {t.content}
              </div>
            ) : (
              <div key={i} className="mr-4 space-y-2">
                {t.content && (
                  <div className="space-y-2 rounded-2xl bg-slate-800/70 px-4 py-2">
                    <SourceText text={t.content} sources={t.sources} />
                    <SourceList text={t.content} sources={t.sources} />
                  </div>
                )}
                {t.error && <p className="text-sm text-red-300">Error: {t.error}</p>}
              </div>
            ),
          )}
          {chat.pending && (
            <div className="mr-4 rounded-2xl bg-slate-800/40 px-4 py-3">
              <Waiting label="Assistant is thinking…" />
            </div>
          )}
          <div ref={endRef} />
        </div>

        <form onSubmit={submit} className="flex gap-2">
          <label htmlFor="chat-input" className="sr-only">
            Message
          </label>
          <input
            id="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your message…"
            className="min-h-11 flex-1 rounded-xl border border-slate-600 bg-slate-950 px-3"
            disabled={chat.pending}
          />
          {chat.pending ? (
            <Button variant="danger" onClick={chat.stop} aria-label="Stop">
              <StopIcon />
            </Button>
          ) : (
            <Button variant="primary" type="submit" aria-label="Send" disabled={!input.trim()}>
              <SendIcon />
            </Button>
          )}
        </form>
      </div>
    </Card>
  );
}
