import type { ExplainResponse } from "../../api/client";
import { Tag } from "../../components/ui/Badges";

const GENERATED_BY = {
  llm: "Yapay zekâ açıklaması",
  mock: "Mock (şablon) açıklama",
  template_fallback: "Kural tabanlı şablon (LLM kullanılamadı)",
};

export function ExplainPanel({ data }: { data: ExplainResponse }) {
  const e = data.explanation;
  return (
    <div className="space-y-3 rounded-xl border border-slate-700 bg-slate-950/60 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Tag tone="sky">{GENERATED_BY[data.generated_by]}</Tag>
        {data.model && <Tag>{data.model}</Tag>}
        {data.cached && <Tag>önbellekten</Tag>}
      </div>
      <p className="text-lg">{e.summary}</p>
      {e.likely_factors.length > 0 && (
        <div>
          <p className="text-sm font-medium text-slate-400">Olası etkenler</p>
          <ul className="list-disc space-y-1 pl-6">{e.likely_factors.map((f) => <li key={f}>{f}</li>)}</ul>
        </div>
      )}
      {e.recommended_actions.length > 0 && (
        <div>
          <p className="text-sm font-medium text-slate-400">Önerilen adımlar</p>
          <ul className="list-disc space-y-1 pl-6">{e.recommended_actions.map((a) => <li key={a}>{a}</li>)}</ul>
        </div>
      )}
      {e.escalate_to_ground && (
        <p className="rounded-lg border border-amber-500/60 bg-amber-950/50 px-3 py-2 text-amber-200">
          Yer ekibine iletilmesi öneriliyor.
        </p>
      )}
      {e.uncertainty && <p className="text-sm text-slate-400">Belirsizlik: {e.uncertainty}</p>}
      {data.ungrounded_numbers.length > 0 && (
        <p className="text-sm text-amber-300">
          Doğrulanamayan sayılar: {data.ungrounded_numbers.join(", ")} (veride karşılığı bulunamadı)
        </p>
      )}
      {(e.sources.length > 0 || data.doc_refs.length > 0) && (
        <details className="text-sm text-slate-400">
          <summary className="cursor-pointer">Kaynaklar</summary>
          <ul className="mt-1 list-disc pl-6">
            {e.sources.map((s) => <li key={s}>{s}</li>)}
            {data.doc_refs.map((d) => (
              <li key={`${d.file}-${d.section}-${d.page}`}>
                {d.file}
                {d.section && ` § ${d.section}`}
                {d.page != null && ` s. ${d.page}`}
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="text-xs text-slate-500">Karar desteğidir, teşhis değildir.</p>
    </div>
  );
}
