import type { Contributor } from "../../api/client";
import { useCatalog } from "../../api/queries";
import { fmtNum, fmtValue } from "../../components/ui/format";

/** "Bu uyarıya katkı" yatay çubukları. */
export function ContributorBars({ contributors }: { contributors: Contributor[] }) {
  const catalog = useCatalog();
  const metricInfo = (name: string) => catalog.data?.metrics.find((m) => m.name === name);

  return (
    <div>
      <p className="mb-2 text-sm font-medium text-slate-400">Contribution to this alert</p>
      <ul className="space-y-2">
        {contributors.map((c) => {
          const info = metricInfo(c.metric);
          const pct = Math.round(c.weight * 100);
          return (
            <li key={c.metric}>
              <div className="mb-1 flex flex-wrap items-baseline justify-between gap-x-3 text-sm">
                <span className="font-medium text-slate-200">{info?.display_name ?? c.metric}</span>
                <span className="text-slate-400">
                  {c.value != null && info && <>now {fmtValue(c.value, info.unit, info.decimals)}</>}
                  {c.baseline != null && info && <> · normal {fmtValue(c.baseline, info.unit, info.decimals)}</>}
                  {c.z != null && <> · z {fmtNum(c.z, 1)}</>}
                  {c.threshold_verified === false && <> · threshold not verified</>}
                </span>
              </div>
              <div
                className="h-3 w-full overflow-hidden rounded-full bg-slate-800"
                role="meter"
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${info?.display_name ?? c.metric} contributes ${pct} percent`}
              >
                <div className="h-full rounded-full bg-sky-400" style={{ width: `${Math.max(pct, 3)}%` }} />
              </div>
              <span className="text-xs text-slate-500">{pct}%</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
