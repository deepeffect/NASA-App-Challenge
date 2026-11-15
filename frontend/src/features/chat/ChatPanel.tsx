/**
 * Legacy sohbet paneli → asistan API'si (bkz. useAssistantChat). Cevaptaki [D1]/[K1] etiketleri kaynak rozetidir.
 * Acil belirti bandı bizim backend'in kural tabanlı taramasından gelir (LLM'den bağımsız).
 */
import { useEffect, useRef, useState, type FormEvent } from "react";

import { EmergencyBanner } from "../../components/ui/EmergencyBanner";
import { SendIcon, StopIcon } from "../../components/ui/icons";
import { Button, Card } from "../../components/ui/primitives";
import { type AssistantSelection, AssistantDataTag, SelectionPending, SourceList, SourceText, Waiting } from "../assistant";
import { useAssistantTexts } from "../assistant/texts";
import { useAssistantChat } from "./useAssistantChat";

// Asistan API'si İngilizce çalışır; öneri soruları bu yüzden İngilizce
const SUGGESTIONS = ["What is my daily report?", "How is my sleep?", "Why is my heart rate high?"];

export function ChatPanel({ sel }: { sel: AssistantSelection }) {
  const t = useAssistantTexts();
  const chat = useAssistantChat(sel);
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [chat.turns, chat.pending]);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || chat.pending || !sel.ready) return;
    void chat.send(input);
    setInput("");
  };

  return (
    <Card
      title={t("chatTitle")}
      actions={
        <div className="flex items-center gap-2">
          <AssistantDataTag />
          {chat.turns.length > 0 && (
            <Button variant="ghost" onClick={chat.reset} className="text-sm">
              {t("clear")}
            </Button>
          )}
        </div>
      }
    >
      <div className="space-y-4">
        {chat.emergency && <EmergencyBanner notice={chat.emergency} onDismiss={chat.dismissEmergency} />}

        <div className="max-h-[28rem] space-y-3 overflow-y-auto pr-1" aria-live="polite">
          {!sel.ready && (
            <SelectionPending status={sel.status} message={sel.message} astronautId={sel.astronautId} day={sel.day} />
          )}
          {sel.ready && chat.turns.length === 0 && !chat.pending && (
            <div className="space-y-2">
              <p className="text-slate-400">{t("chatIntro")}</p>
              <div className="flex flex-wrap gap-2">
                {SUGGESTIONS.map((s) => (
                  <Button key={s} variant="secondary" className="text-sm" onClick={() => void chat.send(s)}>
                    {s}
                  </Button>
                ))}
              </div>
            </div>
          )}
          {chat.turns.map((turn, i) =>
            turn.role === "user" ? (
              <div key={i} className="ml-8 whitespace-pre-wrap rounded-2xl bg-sky-900/40 px-4 py-2">
                {turn.content}
              </div>
            ) : (
              <div key={i} className="mr-4 space-y-2">
                {turn.content && (
                  <div className="space-y-2 rounded-2xl bg-slate-800/70 px-4 py-2">
                    <SourceText text={turn.content} sources={turn.sources} />
                    <SourceList text={turn.content} sources={turn.sources} />
                  </div>
                )}
                {turn.error && (
                  <p className="text-sm text-red-300">
                    {t("error")}: {turn.error}
                  </p>
                )}
              </div>
            ),
          )}
          {chat.pending && (
            <div className="mr-4 rounded-2xl bg-slate-800/40 px-4 py-3">
              <Waiting label={t("thinking")} />
            </div>
          )}
          <div ref={endRef} />
        </div>

        <form onSubmit={submit} className="flex gap-2">
          <label htmlFor="chat-input" className="sr-only">
            {t("messageLabel")}
          </label>
          <input
            id="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t("placeholder")}
            className="min-h-11 flex-1 rounded-xl border border-slate-600 bg-slate-950 px-3"
            disabled={chat.pending || !sel.ready}
          />
          {chat.pending ? (
            <Button variant="danger" onClick={chat.stop} aria-label={t("stop")}>
              <StopIcon />
            </Button>
          ) : (
            <Button variant="primary" type="submit" aria-label={t("send")} disabled={!input.trim() || !sel.ready}>
              <SendIcon />
            </Button>
          )}
        </form>
      </div>
    </Card>
  );
}
