/**
 * Asistan metnini markdown olarak gösterir (kalın, liste, başlık, emoji, GFM tablo) ve
 * [D1]/[K1] etiketlerini kaynak rozetine çevirir (D → 📊 veri etiketi, K → 📄 belge adı).
 * Yöntem: etiketler önce `[D1](#src:D1)` linkine dönüştürülür, özel `a` bileşeni rozeti çizer.
 * Ham HTML işlenmez (react-markdown varsayılanı) → LLM çıktısından HTML enjekte edilemez.
 */
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import type { SourceRef, Sources } from "./api";
import { tx, useAssistantTexts } from "./texts";

const TAG = /\[([DK]\d+)\]/g;
const SRC_PREFIX = "#src:";

function sourceTitle(s: SourceRef): string {
  if (s.type === "data") {
    const val = s.value !== undefined && s.value !== null ? `${s.value}${s.unit ? ` ${s.unit}` : ""}` : "";
    return [s.label, val, s.status ? tx("status", { s: s.status }) : ""].filter(Boolean).join(" · ");
  }
  return `${s.label}${s.text ? ` — ${s.text}` : ""}`;
}

export function SourceBadge({ tag, source }: { tag: string; source?: SourceRef }) {
  const t = useAssistantTexts();
  if (!source) return <span className="text-slate-500">[{tag}]</span>;
  const isData = source.type === "data";
  return (
    <span
      title={sourceTitle(source)}
      className={`mx-0.5 inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-px align-baseline text-xs font-normal ${
        isData ? "border-sky-700/70 bg-sky-950/60 text-sky-200" : "border-violet-700/70 bg-violet-950/60 text-violet-200"
      }`}
    >
      <span aria-hidden="true">{isData ? "📊" : "📄"}</span>
      <span className="sr-only">{isData ? t("srData") : t("srDoc")}</span>
      {source.label}
    </span>
  );
}

/** [D2][D2] → [D2]; sonra her etiketi markdown linkine çevir. */
function linkifyTags(text: string): string {
  return text
    .replace(/(\[([DK]\d+)\])(?:\s*\[\2\])+/g, "$1")
    .replace(TAG, (_m, tag: string) => `[${tag}](${SRC_PREFIX}${tag})`);
}

function components(sources: Sources | undefined): Components {
  return {
    a: ({ href, children }) => {
      if (href?.startsWith(SRC_PREFIX)) {
        const tag = href.slice(SRC_PREFIX.length);
        return <SourceBadge tag={tag} source={sources?.[tag]} />;
      }
      // Çevrim dışı sistem: dış linkler tıklanabilir yapılmaz
      return <span className="underline decoration-dotted">{children}</span>;
    },
    h1: ({ children }) => <p className="text-lg font-semibold text-slate-100">{children}</p>,
    h2: ({ children }) => <p className="text-base font-semibold text-slate-100">{children}</p>,
    h3: ({ children }) => <p className="font-semibold text-slate-100">{children}</p>,
    p: ({ children }) => <p className="leading-relaxed">{children}</p>,
    em: ({ children }) => <em className="text-slate-400">{children}</em>,
    strong: ({ children }) => <strong className="font-semibold text-slate-50">{children}</strong>,
    ul: ({ children }) => <ul className="list-disc space-y-1 pl-5 marker:text-slate-500">{children}</ul>,
    ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5 marker:text-slate-500">{children}</ol>,
    li: ({ children }) => <li className="leading-relaxed">{children}</li>,
    code: ({ children }) => <code className="rounded bg-slate-800 px-1 text-sm">{children}</code>,
    table: ({ children }) => (
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">{children}</table>
      </div>
    ),
    th: ({ children }) => <th className="border-b border-slate-700 px-2 py-1 text-left font-medium">{children}</th>,
    td: ({ children }) => <td className="border-b border-slate-800 px-2 py-1">{children}</td>,
  };
}

export function SourceText({ text, sources }: { text: string; sources?: Sources }) {
  return (
    <div className="space-y-2">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components(sources)}>
        {linkifyTags(text)}
      </ReactMarkdown>
    </div>
  );
}

/** Metinde geçen kaynakların açılır listesi (belge alıntısının tamamını okumak için). */
export function SourceList({ text, sources }: { text: string; sources?: Sources }) {
  const t = useAssistantTexts();
  if (!sources) return null;
  const used = [...new Set([...text.matchAll(TAG)].map((m) => m[1]))].filter((t) => sources[t]);
  if (used.length === 0) return null;
  return (
    <details className="text-sm text-slate-400">
      <summary className="cursor-pointer select-none">{t("sources", { n: used.length })}</summary>
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
