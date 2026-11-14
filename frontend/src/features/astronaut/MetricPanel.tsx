import type { MetricSnapshot } from "../../api/client";
import { useCatalog, useMetricSeries } from "../../api/queries";
import { useAsOf } from "../../app/AsOfContext";
import { MetricChart } from "../../components/charts/MetricChart";
import { fmtNum, fmtValue } from "../../components/ui/format";
import { SYSTEM_LABELS } from "../../components/ui/labels";
import { Card, QueryState } from "../../components/ui/primitives";

const DAY_OPTIONS = [14, 30, 60, 180];

export function MetricPanel({
  astronautId,
  metric,
  onMetricChange,
  days,
  onDaysChange,
  latest,
}: {
  astronautId: string;
  metric: string;
  onMetricChange: (m: string) => void;
  days: number;
  onDaysChange: (d: number) => void;
  latest?: MetricSnapshot;
}) {
  const { asOf } = useAsOf();
  const catalog = useCatalog();
  const series = useMetricSeries(astronautId, metric, days, asOf);

  return (
    <Card
      title="Metric chart"
      actions={
        <div className="flex flex-wrap gap-2">
          <select
            aria-label="Select metric"
            value={metric}
            onChange={(e) => onMetricChange(e.target.value)}
            className="min-h-11 rounded-xl border border-slate-600 bg-slate-800 px-3"
          >
            {catalog.data?.systems.map((s) => (
              <optgroup key={s.id} label={SYSTEM_LABELS[s.id]}>
                {s.metrics.map((name) => {
                  const m = catalog.data!.metrics.find((x) => x.name === name);
                  return (
                    <option key={name} value={name}>
                      {m?.display_name ?? name}
                    </option>
                  );
                })}
              </optgroup>
            ))}
          </select>
          <select
            aria-label="Day range"
            value={days}
            onChange={(e) => onDaysChange(Number(e.target.value))}
            className="min-h-11 rounded-xl border border-slate-600 bg-slate-800 px-3"
          >
            {DAY_OPTIONS.map((d) => (
              <option key={d} value={d}>
                Last {d} days
              </option>
            ))}
          </select>
        </div>
      }
    >
      {latest && latest.value != null && (
        <p className="mb-3 text-lg">
          Latest: <strong>{fmtValue(latest.value, latest.unit, 2)}</strong>
          {latest.baseline_mean != null && (
            <span className="text-slate-400"> · personal normal {fmtValue(latest.baseline_mean, latest.unit, 2)}</span>
          )}
          {latest.z7 != null && <span className="text-slate-400"> · 7-day z {fmtNum(latest.z7, 1)}</span>}
        </p>
      )}
      <QueryState query={series} loadingLabel="Loading series…">
        {(data) => <MetricChart series={data} />}
      </QueryState>
    </Card>
  );
}
