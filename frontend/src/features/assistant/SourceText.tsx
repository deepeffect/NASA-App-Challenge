/**
 * Asistan metnini gösterir: [D1]/[K1] etiketlerini kaynak rozetine çevirir
 * (D → 📊 veri etiketi, K → 📄 belge adı) ve basit markdown'ı (#, **kalın**, _satır_, - liste) işler.
 * Aynı rozet art arda tekrar ederse ([D2][D2]) bir kez gösterilir.
 */
import { Fragment, type ReactNode } from "react";

import type { SourceRef, Sources } from "./api";

const TAG = /\[([DK]\d+)\]/g;

function sourceTitle(s: SourceRef): string {
  if (s.type === "data") {
    const val = s.value !== undefined && s.value !== null ? `${s.value}${s.unit ? ` ${s.unit}` : ""}` : "";
    return [s.label, val, s.status ? `status ${s.status}` : ""].filter(Boolean).join(" · ");
  }
  return `${s.label}${s.text ? ` — ${s.text}` : ""}`;
}

export function SourceBadge({ tag, source }: { tag: string; source?: SourceRef }) {
  if (!source) return <span className="text-slate-500">[{tag}]</span>;
  const isData = source.type === "data";
  return (
    <span
      title={sourceTitle(source)}
      className={`mx-0.5 inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-px align-baseline text-xs ${
        isData ? "border-sky-700/70 bg-sky-950/60 text-sky-200" : "border-violet-700/70 bg-violet-950/60 text-violet-200"
      }`}
    >
      <span aria-hidden="true">{isData ? "📊" : "📄"}</span>
      <span className="sr-only">{isData ? "Data source:" : "Document source:"}</span>
      {source.label}
    </span>
  );
}

function bold(text: string, key: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={`${key}-b${i}`}>{part.slice(2, -2)}</strong>
    ) : (
      <Fragment key={`${key}-t${i}`}>{part}</Fragment>
    ),
  );
}

/** Tek satırı rozetli parçalara böler. */
function inline(text: string, sources: Sources | undefined, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let prevTag: string | null = null;
  for (const m of text.matchAll(TAG)) {
    const idx = m.index ?? 0;
    const between = text.slice(last, idx);
    if (between) {
      out.push(...bold(between, `${key}-${idx}`));
      if (between.trim()) prevTag = null;
    }
    const tag = m[1];
    if (tag !== prevTag) out.push(<SourceBadge key={`${key}-s${idx}`} tag={tag} source={sources?.[tag]} />);
    prevTag = tag;
    last = idx + m[0].length;
  }
  if (last < text.length) out.push(...bold(text.slice(last), `${key}-end`));
  return out;
}

/** Çok satırlı metin: başlıklar, italik meta satırı, liste ve paragraflar. */
export function SourceText({ text, sources }: { text: string; sources?: Sources }) {
  const blocks = text.replace(/\r\n/g, "\n").split(/\n{2,}/);
  return (
    <div className="space-y-2">
      {blocks.map((block, bi) => (
        <div key={bi} className="space-y-1">
          {block.split("\n").map((raw, li) => {
            const line = raw.trimEnd();
            const k = `${bi}-${li}`;
            if (!line.trim()) return null;
            const h = /^#{1,3}\s+(.*)$/.exec(line);
            if (h) {
              return (
                <p key={k} className="text-base font-semibold text-slate-100">
                  {inline(h[1], sources, k)}
                </p>
              );
            }
            const meta = /^_(.+)_$/.exec(line.trim());
            if (meta) {
              return (
                <p key={k} className="text-sm text-slate-500">
                  {meta[1]}
                </p>
              );
            }
            const item = /^\s*[-*]\s+(.*)$/.exec(line);
            if (item) {
              return (
                <p key={k} className="pl-4 -indent-3">
                  • {inline(item[1], sources, k)}
                </p>
              );
            }
            return <p key={k}>{inline(line, sources, k)}</p>;
          })}
        </div>
      ))}
    </div>
  );
}

/** Metinde geçen kaynakların açılır listesi (belge alıntısının tamamını okumak için). */
export function SourceList({ text, sources }: { text: string; sources?: Sources }) {
  if (!sources) return null;
  const used = [...new Set([...text.matchAll(TAG)].map((m) => m[1]))].filter((t) => sources[t]);
  if (used.length === 0) return null;
  return (
    <details className="text-sm text-slate-400">
      <summary className="cursor-pointer select-none">Sources ({used.length})</summary>
      <ul className="mt-2 space-y-2">
        {used.map((t) => (
          <li key={t} className="flex flex-col gap-1">
            <span>
              <SourceBadge tag={t} source={sources[t]} />
            </span>
            <span>{sourceTitle(sources[t])}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}
