/**
 * "Asistana sor": varsayılan olarak KAPALI bir kart; açılınca `POST /api/chat` (SSE) ile serbest sohbet.
 * Prototipte yoktur (ek). Sakin kalsın diye sadece mesaj balonları ve tek satırlık durum gösterilir.
 *
 *  - Asistan sadece giriş yapan astronotun verisine bakar (backend token'dan bilir) ve teşhis koymaz.
 *  - Sayılar modelden değil araç sonuçlarından gelir; doğrulanamayan sayı varsa backend bildirir, burada gösterilir.
 *  - Asistan katmanı açıksa (backend `ASSISTANT_LAYER_URL`) cevaptaki `[D1]` / `[K1]` etiketleri kaynak rozetine çevrilir;
 *    karşılıkları `done.sources` ile gelir ve cevabın altında listelenir (ikon + metin, sadece renk değil).
 *  - Acil belirti kural tabanlıdır: modelden ÖNCE ve model kapalıyken de gelir; kutu sohbetin üstünde kalır.
 *  - Sohbet hiçbir yere kaydedilmez ve Dünya'ya gönderilmez; çıkışta ve sayfa yenilenince silinir.
 */
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";

import type { EmergencyNotice, SourceRef } from "../../api/client";
import { StationApiError } from "../../api/station";
import { type ChatMessage, isUnauthorized, streamChat } from "./api";
import { useT } from "./texts";

interface Turn extends ChatMessage {
  id: number;
  /** Süren araç çağrısı sayısı (veriye bakılıyor). */
  tools: number;
  /** Akış bitti (cevap tamam, durduruldu veya hata). */
  settled: boolean;
  error?: string;
  /** Verilerle doğrulanamayan sayılar (backend'in sayı denetimi). */
  ungrounded: string[];
  /** `[D1]` / `[K1]` etiketlerinin karşılıkları (asistan katmanı); yoksa boş. */
  sources: Record<string, SourceRef>;
}

const SOURCE_ICON: Record<SourceRef["type"], string> = { data: "📊", knowledge: "📄" };
const INLINE = /(\*\*[^*\n]+\*\*|\[[DK]\d+\])/g;

function sourceTitle(src: SourceRef): string {
  if (src.type === "knowledge") return src.text ? `${src.label}: ${src.text}` : src.label;
  const value = src.value == null ? "" : `: ${src.value}${src.unit ? ` ${src.unit}` : ""}`;
  return `${src.label}${value}`;
}

/** Cevap metni: `**kalın**` ve karşılığı olan `[D1]` / `[K1]` etiketleri işlenir; gerisi düz metin kalır. */
function renderAnswer(content: string, sources: Record<string, SourceRef>): ReactNode[] {
  return content.split(INLINE).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <b key={i}>{part.slice(2, -2)}</b>;
    const key = /^\[([DK]\d+)\]$/.exec(part)?.[1];
    const src = key ? sources[key] : undefined;
    if (!key || !src) return part;
    return (
      <span key={i} className="src" title={sourceTitle(src)} data-source={key}>
        {SOURCE_ICON[src.type]} {key}
      </span>
    );
  });
}

export function AskAssistant({ onUnauthorized }: { onUnauthorized: (message: string) => void }) {
  const { t } = useT();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [emergency, setEmergency] = useState<EmergencyNotice | null>(null);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const nextId = useRef(1);

  useEffect(() => () => abortRef.current?.abort(), []); // ekrandan çıkınca akışı kes

  const ask = async (text: string) => {
    const question = text.trim();
    if (!question || streaming) return;
    const history: ChatMessage[] = [
      ...turns.filter((x) => x.content.trim()).map(({ role, content }) => ({ role, content })),
      { role: "user", content: question },
    ];
    const userId = nextId.current;
    const answerId = userId + 1;
    nextId.current += 2;
    setTurns((all) => [
      ...all,
      { id: userId, role: "user", content: question, tools: 0, settled: true, ungrounded: [], sources: {} },
      { id: answerId, role: "assistant", content: "", tools: 0, settled: false, ungrounded: [], sources: {} },
    ]);
    setDraft("");
    setStreaming(true);

    const patch = (change: (turn: Turn) => Turn) => setTurns((all) => all.map((x) => (x.id === answerId ? change(x) : x)));
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamChat(
        history,
        {
          onToken: (chunk) => patch((x) => ({ ...x, content: x.content + chunk })),
          onToolCall: () => patch((x) => ({ ...x, tools: x.tools + 1 })),
          onToolResult: () => patch((x) => ({ ...x, tools: Math.max(0, x.tools - 1) })),
          onEmergency: (notice) => {
            if (notice.triggered) setEmergency(notice);
          },
          // `done.message` cevabın yetkili hali; boşsa (hata) akıştan birikeni koru.
          onDone: (done) =>
            patch((x) => ({ ...x, content: done.message || x.content, ungrounded: done.ungrounded_numbers ?? [], sources: done.sources ?? {} })),
          onError: (e) => patch((x) => ({ ...x, error: e.message })),
        },
        controller.signal,
      );
    } catch (e) {
      if (isUnauthorized(e)) onUnauthorized((e as StationApiError).message);
      else if (!controller.signal.aborted) patch((x) => ({ ...x, error: e instanceof StationApiError ? e.message : t("askFailed") }));
    } finally {
      patch((x) => ({ ...x, tools: 0, settled: true, error: x.error ?? (controller.signal.aborted && !x.content ? t("askStopped") : undefined) }));
      setStreaming(false);
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void ask(draft);
  };

  return (
    <details className="card more ask">
      <summary>{t("askTitle")}</summary>
      <div className="stack">
        {turns.length === 0 ? <p className="calm">{t("askIntro")}</p> : null}

        {emergency ? (
          <div className="ground" role="alert" data-emergency>
            <p>
              <b>{emergency.protocol.title}</b>
            </p>
            <p>{emergency.message}</p>
            <ol>
              {emergency.protocol.steps.map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ol>
            {emergency.protocol.verified ? null : <p className="muted">{t("protocolPlaceholder")}</p>}
          </div>
        ) : null}

        <div className="cilog" aria-live="polite">
          {turns.map((turn) =>
            turn.role === "user" ? (
              <div key={turn.id} className="msg me">
                {turn.content}
              </div>
            ) : (
              <div key={turn.id} className="msg bot" data-settled={turn.settled ? "true" : undefined}>
                {turn.content
                  ? renderAnswer(turn.content, turn.sources)
                  : turn.settled
                    ? (turn.error ?? t("askFailed"))
                    : turn.tools > 0
                      ? t("askLooking")
                      : t("askWriting")}
                {Object.keys(turn.sources).some((key) => turn.content.includes(`[${key}]`)) ? (
                  <ul className="srclist" aria-label={t("sourcesTitle")}>
                    {Object.entries(turn.sources)
                      .filter(([key]) => turn.content.includes(`[${key}]`))
                      .map(([key, src]) => (
                        <li key={key}>
                          <span className="src">
                            {SOURCE_ICON[src.type]} {key}
                          </span>{" "}
                          <span className="muted">{src.type === "data" ? t("sourceData") : t("sourceKnowledge")}:</span> {sourceTitle(src)}
                          {src.type === "data" && (src.status === "GREEN" || src.status === "YELLOW" || src.status === "RED") ? (
                            <span className="muted"> · {t(`sourceStatus${src.status}`)}</span>
                          ) : null}
                        </li>
                      ))}
                  </ul>
                ) : null}
                {turn.ungrounded.length > 0 ? (
                  <>
                    {"\n"}
                    <span className="muted">{t("ungrounded", { list: turn.ungrounded.join(", ") })}</span>
                  </>
                ) : null}
              </div>
            ),
          )}
        </div>

        <form className="cirow" onSubmit={onSubmit}>
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={t("askPlaceholder")}
            aria-label={t("askLabel")}
            autoComplete="off"
            maxLength={2000}
          />
          {streaming ? (
            <button type="button" onClick={() => abortRef.current?.abort()}>
              {t("stop")}
            </button>
          ) : (
            <button type="submit">{t("send")}</button>
          )}
        </form>

        <p className="muted">{t("askStays")}</p>
      </div>
    </details>
  );
}
