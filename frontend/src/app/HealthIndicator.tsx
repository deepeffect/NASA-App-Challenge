/** Header'daki sistem durumu: LLM erişimi. LLM yokken de uyarıların çalıştığını açıkça söyler. */
import { useHealth } from "../api/queries";

export function HealthIndicator() {
  const { data, isError } = useHealth();
  if (isError) {
    return <span className="text-sm text-red-300">● Backend unreachable</span>;
  }
  if (!data) return null;
  const { llm } = data;
  if (llm.provider === "mock") {
    return <span className="text-sm text-sky-300" title="LLM_PROVIDER=mock">● Assistant: mock mode</span>;
  }
  if (llm.reachable && llm.model_available) {
    return <span className="text-sm text-emerald-300">● Assistant: {llm.model}</span>;
  }
  return (
    <span className="text-sm text-amber-300" title={llm.error ?? undefined}>
      ● Assistant offline — alerts still working
    </span>
  );
}
