import { useEffect, useRef, useState, type FormEvent } from "react";

import { useAsOf } from "../../app/AsOfContext";
import { EmergencyBanner } from "../../components/ui/EmergencyBanner";
import { DatabaseIcon, SendIcon, StopIcon } from "../../components/ui/icons";
import { TOOL_LABELS } from "../../components/ui/labels";
import { Button, Card } from "../../components/ui/primitives";
import { useChatStream, type ToolActivity } from "./useChatStream";

const SUGGESTIONS = ["Bugün nasılım?", "Son günlerde uykum nasıl?", "Radyasyon dozum ne durumda?"];

export function ChatPanel({ astronautId }: { astronautId: string }) {
  const { asOf } = useAsOf();
  const chat = useChatStream(astronautId, asOf);
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [chat.turns]);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!input.trim()) return;
    void chat.send(input);
    setInput("");
  };

  return (
    <Card
      title="Sağlık asistanı"
      actions={
        chat.turns.length > 0 && (
          <Button variant="ghost" onClick={chat.reset} className="text-sm">
            Temizle
          </Button>
        )
      }
    >
      <div className="space-y-4">
        {chat.emergency && <EmergencyBanner notice={chat.emergency} onDismiss={chat.dismissEmergency} />}

        <div className="max-h-[28rem] space-y-3 overflow-y-auto pr-1" aria-live="polite">
          {chat.turns.length === 0 && (
            <div className="space-y-2">
              <p className="text-slate-400">Sağlık verilerin hakkında soru sor. Asistan teşhis koymaz, karar desteği verir.</p>
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
              <div key={i} className="ml-8 rounded-2xl bg-sky-900/40 px-4 py-2">
                {t.content}
              </div>
            ) : (
              <div key={i} className="mr-4 space-y-2">
                {t.tools.length > 0 && <ToolChips tools={t.tools} />}
                {t.thinking && (
                  <details className="text-sm text-slate-500">
                    <summary className="cursor-pointer">Düşünce süreci</summary>
                    <p className="whitespace-pre-wrap">{t.thinking}</p>
                  </details>
                )}
                {(t.content || (chat.streaming && i === chat.turns.length - 1)) && (
                  <div className="whitespace-pre-wrap rounded-2xl bg-slate-800/70 px-4 py-2">
                    {t.content}
                    {chat.streaming && i === chat.turns.length - 1 && <span className="animate-pulse">▍</span>}
                  </div>
                )}
                {t.degraded && (
                  <p className="text-sm text-amber-300">Asistan çevrim dışı; kural tabanlı yedek cevap gösteriliyor.</p>
                )}
                {t.ungrounded && t.ungrounded.length > 0 && (
                  <p className="text-sm text-amber-300">Doğrulanamayan sayılar: {t.ungrounded.join(", ")}</p>
                )}
                {t.error && <p className="text-sm text-red-300">Hata: {t.error}</p>}
              </div>
            ),
          )}
          <div ref={endRef} />
        </div>

        <form onSubmit={submit} className="flex gap-2">
          <label htmlFor="chat-input" className="sr-only">
            Mesaj
          </label>
          <input
            id="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Mesajını yaz…"
            className="min-h-11 flex-1 rounded-xl border border-slate-600 bg-slate-950 px-3"
            disabled={chat.streaming}
          />
          {chat.streaming ? (
            <Button variant="danger" onClick={chat.stop} aria-label="Durdur">
              <StopIcon />
            </Button>
          ) : (
            <Button variant="primary" type="submit" aria-label="Gönder" disabled={!input.trim()}>
              <SendIcon />
            </Button>
          )}
        </form>
      </div>
    </Card>
  );
}

function ToolChips({ tools }: { tools: ToolActivity[] }) {
  return (
    <ul className="flex flex-wrap gap-2">
      {tools.map((tool) => (
        <li
          key={tool.id}
          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-sm ${
            tool.status === "running"
              ? "border-sky-600/60 text-sky-300"
              : tool.status === "ok"
                ? "border-slate-600 text-slate-400"
                : "border-red-500/60 text-red-300"
          }`}
        >
          <DatabaseIcon className={`h-4 w-4 ${tool.status === "running" ? "animate-pulse" : ""}`} />
          {tool.status === "running" ? "Veri alınıyor: " : tool.status === "ok" ? "✓ " : "✗ "}
          {TOOL_LABELS[tool.name] ?? tool.name}
        </li>
      ))}
    </ul>
  );
}
