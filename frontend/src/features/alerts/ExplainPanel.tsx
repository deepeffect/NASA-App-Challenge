import type { ExplainResponse } from "../../api/client";
import { Tag } from "../../components/ui/Badges";

const GENERATED_BY = {
  llm: "AI explanation",
  mock: "Mock (template) explanation",
  template_fallback: "Rule-based template (LLM unavailable)",
};

export function ExplainPanel({ data }: { data: ExplainResponse }) {
  const e = data.explanation;
  return (
    <div className="space-y-3 rounded-xl border border-slate-700 bg-slate-950/60 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Tag tone="sky">{GENERATED_BY[data.generated_by]}</Tag>
        {data.model && data.generated_by === "llm" && <Tag>{data.model}</Tag>}
        {data.cached && <Tag>cached</Tag>}
      </div>
      <p className="text-lg">{e.summary}</p>
      {e.likely_factors.length > 0 && (
        <div>
          <p className="text-sm font-medium text-slate-400">Possible factors</p>
          <ul className="list-disc space-y-1 pl-6">{e.likely_factors.map((f, i) => <li key={i}>{f}</li>)}</ul>
        </div>
      )}
      {e.recommended_actions.length > 0 && (
        <div>
          <p className="text-sm font-medium text-slate-400">Recommended steps</p>
          <ul className="list-disc space-y-1 pl-6">{e.recommended_actions.map((a, i) => <li key={i}>{a}</li>)}</ul>
        </div>
      )}
      {e.escalate_to_ground && (
        <p className="rounded-lg border border-amber-500/60 bg-amber-950/50 px-3 py-2 text-amber-200">
          Escalation to the ground team is recommended.
        </p>
      )}
      {e.uncertainty && <p className="text-sm text-slate-400">Uncertainty: {e.uncertainty}</p>}
      {data.ungrounded_numbers.length > 0 && (
        <p className="text-sm text-amber-300">
          Unverified numbers: {data.ungrounded_numbers.join(", ")} (not found in the data)
        </p>
      )}
      {(e.sources.length > 0 || data.doc_refs.length > 0) && (
        <details className="text-sm text-slate-400">
          <summary className="cursor-pointer">Sources</summary>
          <ul className="mt-1 list-disc pl-6">
            {e.sources.map((s, i) => <li key={`s${i}`}>{s}</li>)}
            {data.doc_refs.map((d) => (
              <li key={`${d.file}-${d.section}-${d.page}`}>
                {d.file}
                {d.section && ` § ${d.section}`}
                {d.page != null && ` p. ${d.page}`}
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="text-xs text-slate-500">Decision support, not a diagnosis.</p>
    </div>
  );
}
