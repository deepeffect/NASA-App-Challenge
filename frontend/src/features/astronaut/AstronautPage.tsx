/**
 * Astronot detayı: sistem skorları, olay kartları, metrik grafiği, brifing, sohbet.
 * Bu sayfa alerts ve chat feature'larını sadece public API'leri (index.ts) üzerinden kullanır.
 */
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import { SEVERITY_RANK_UI } from "./severity";
import { useSummary } from "../../api/queries";
import { useAsOf } from "../../app/AsOfContext";
import { StatusBadge } from "../../components/ui/Badges";
import { fmtDateTime, fmtNum } from "../../components/ui/format";
import { ArrowLeftIcon } from "../../components/ui/icons";
import { Card, QueryState } from "../../components/ui/primitives";
import { EventList } from "../alerts";
import { ChatPanel } from "../chat";
import { BriefingCard } from "./BriefingCard";
import { MetricPanel } from "./MetricPanel";
import { SystemScoreCard } from "./SystemScoreCard";

export function AstronautPage() {
  const { id = "" } = useParams();
  const { asOf } = useAsOf();
  const summary = useSummary(id, asOf);
  const [metric, setMetric] = useState<string | null>(null);
  const [days, setDays] = useState(30);

  // Varsayılan metrik: en ciddi aktif olayın ilk metriği
  useEffect(() => {
    if (metric || !summary.data) return;
    const worst = [...summary.data.active_events].sort(
      (a, b) => SEVERITY_RANK_UI[b.severity] - SEVERITY_RANK_UI[a.severity],
    )[0];
    setMetric(worst?.contributors[0]?.metric ?? "sleep_duration");
  }, [summary.data, metric]);

  const showMetric = (m: string) => {
    setMetric(m);
    document.getElementById("metric-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <QueryState query={summary} loadingLabel="Astronot verisi yükleniyor…">
      {(data) => (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <Link to="/" className="rounded-lg p-2 text-slate-400 hover:bg-slate-800" aria-label="Mürettebata dön">
                <ArrowLeftIcon className="h-6 w-6" />
              </Link>
              <div>
                <h1 className="text-3xl font-bold">{data.astronaut.name}</h1>
                <p className="text-slate-400">
                  {data.astronaut.role} · Görev günü {data.mission.mission_day} · Son ölçüm{" "}
                  {fmtDateTime(data.last_measurement_at)}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <StatusBadge status={data.overall.status} size="lg" />
              <span className="text-2xl font-semibold tabular-nums">{fmtNum(data.overall.score, 0)}/100</span>
              <Link
                to={`/checkin/${data.astronaut.id}`}
                className="inline-flex min-h-11 items-center rounded-xl border border-slate-600 bg-slate-800 px-4 hover:bg-slate-700"
              >
                Günlük check-in
              </Link>
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <div className="space-y-6 lg:col-span-2">
              <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
                {data.systems.map((s) => (
                  <SystemScoreCard key={s.system} score={s} />
                ))}
              </div>

              <Card title="Aktif uyarılar">
                <EventList events={data.active_events} onShowMetric={showMetric} />
              </Card>

              <div id="metric-panel">
                {metric && (
                  <MetricPanel
                    astronautId={data.astronaut.id}
                    metric={metric}
                    onMetricChange={setMetric}
                    days={days}
                    onDaysChange={setDays}
                    latest={data.latest.find((l) => l.metric === metric)}
                  />
                )}
              </div>
            </div>

            <aside className="space-y-6">
              <BriefingCard astronautId={data.astronaut.id} />
              <div className="lg:sticky lg:top-40">
                <ChatPanel astronautId={data.astronaut.id} />
              </div>
            </aside>
          </div>
        </div>
      )}
    </QueryState>
  );
}
