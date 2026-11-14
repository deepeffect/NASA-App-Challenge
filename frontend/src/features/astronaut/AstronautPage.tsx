/**
 * Astronot detayı ("sağlık gezgini" düzeni):
 *   seçici → kimlik satırı → özet şeridi → skor geçmişi grafiği → sistem kartları
 *   → (uyarılar + brifing) | bu günün ölçümleri → metrik grafiği + sohbet.
 * Bu sayfa alerts ve chat feature'larını sadece public API'leri (index.ts) üzerinden kullanır.
 */
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import { SEVERITY_RANK_UI } from "./severity";
import { useScoreHistory, useSummary } from "../../api/queries";
import { useAsOf } from "../../app/AsOfContext";
import { ScoreHistoryChart } from "../../components/charts/ScoreCharts";
import { addDays, fmtDate, fmtDateTime } from "../../components/ui/format";
import { ArrowLeftIcon } from "../../components/ui/icons";
import { Card, ErrorBox, QueryState, Spinner } from "../../components/ui/primitives";
import { EventList } from "../alerts";
import { ChatPanel } from "../chat";
import { AstronautPicker } from "./AstronautPicker";
import { BriefingCard } from "./BriefingCard";
import { MetricPanel } from "./MetricPanel";
import { ReadingsTable } from "./ReadingsTable";
import { SummaryStrip } from "./SummaryStrip";
import { SystemScoreCard } from "./SystemScoreCard";

const HISTORY_OPTIONS = [30, 60, 90];

export function AstronautPage() {
  const { id = "" } = useParams();
  // key: astronot değişince seçili metrik ve grafik penceresi sıfırlansın
  return <AstronautView key={id} id={id} />;
}

function AstronautView({ id }: { id: string }) {
  const { asOf, setAsOf } = useAsOf();
  const summary = useSummary(id, asOf);
  const [metric, setMetric] = useState<string | null>(null);
  const [days, setDays] = useState(30);
  const [historyDays, setHistoryDays] = useState(30);

  // Skor grafiği penceresi: seçili gün pencerenin içindeyken pencere sabit kalır (imleç gezer),
  // dışına çıkınca pencere seçili günde bitecek şekilde kayar.
  const [anchor, setAnchor] = useState<string | null>(null);
  const selectedDate = summary.data?.mission.as_of ?? null;
  const windowEnd =
    anchor && selectedDate && selectedDate <= anchor && selectedDate >= addDays(anchor, -(historyDays - 1))
      ? anchor
      : selectedDate;
  useEffect(() => {
    if (windowEnd && windowEnd !== anchor) setAnchor(windowEnd);
  }, [windowEnd, anchor]);
  const history = useScoreHistory(id, historyDays, windowEnd);

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
      {(data) => {
        const { mission } = data;
        const selectDay = (date: string) => setAsOf(date === mission.latest_date ? null : date);
        return (
          <div className="flex flex-col gap-4">
            <header className="flex items-start gap-3">
              <Link to="/" className="mt-0.5 rounded-lg p-1.5 text-slate-400 hover:bg-slate-800" aria-label="Mürettebata dön">
                <ArrowLeftIcon className="h-6 w-6" />
              </Link>
              <div>
                <h1 className="text-[28px] font-bold leading-tight tracking-tight">{data.astronaut.name}</h1>
                <p className="mt-1 max-w-[68ch] text-slate-300">
                  Seçili gün için sağlık skorları, her ölçümün kişisel normale göre durumu ve yapılabilecekler. Günü
                  değiştirmek için üstteki kaydırıcıyı kullanın ya da skor grafiğinde bir güne tıklayın.
                </p>
              </div>
            </header>

            <AstronautPicker currentId={data.astronaut.id} />

            <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-slate-300">
              <span>
                <b className="font-semibold text-slate-100">{data.astronaut.id}</b>
              </span>
              {data.astronaut.role && (
                <span>
                  Rol <b className="font-semibold text-slate-100">{data.astronaut.role}</b>
                </span>
              )}
              <span>
                Görev günü <b className="font-semibold text-slate-100">{mission.mission_day}</b> / {mission.total_days}
              </span>
              <span>
                Tarih <b className="font-semibold text-slate-100">{fmtDate(mission.as_of)}</b>
              </span>
              <span>
                Son ölçüm <b className="font-semibold text-slate-100">{fmtDateTime(data.last_measurement_at)}</b>
              </span>
            </div>

            <SummaryStrip data={data} bands={history.data?.bands} />

            <Card
              title="Sağlık skoru geçmişi"
              actions={
                <select
                  aria-label="Skor geçmişi aralığı"
                  value={historyDays}
                  onChange={(e) => setHistoryDays(Number(e.target.value))}
                  className="min-h-10 rounded-xl border border-slate-600 bg-slate-900 px-2.5"
                >
                  {HISTORY_OPTIONS.map((d) => (
                    <option key={d} value={d}>
                      {d} gün
                    </option>
                  ))}
                </select>
              }
            >
              {history.isPending && <Spinner label="Skor geçmişi hesaplanıyor (ilk açılışta birkaç saniye sürebilir)…" />}
              {history.isError && <ErrorBox error={history.error} />}
              {history.data && (
                <>
                  <ScoreHistoryChart history={history.data} selected={selectedDate} onSelect={selectDay} />
                  <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-slate-400">
                    <span>
                      <span className="mr-1.5 inline-block w-4 border-t-2 align-middle" style={{ borderColor: "var(--series)" }} />
                      Genel skor (her gün, o güne kadarki veriyle; en zayıf sistemin skoru)
                    </span>
                    <span>
                      Seçili gün: görev günü {mission.mission_day} · {fmtDate(mission.as_of)}
                    </span>
                  </p>
                </>
              )}
            </Card>

            <section className="grid grid-cols-1 gap-3 min-[421px]:grid-cols-2 lg:grid-cols-3" aria-label="Sistem skorları">
              {data.systems.map((s) => (
                <SystemScoreCard
                  key={s.system}
                  score={s}
                  history={history.data?.days}
                  selectedDate={selectedDate}
                  mainConcern={data.overall.worst_system === s.system}
                />
              ))}
            </section>

            <section className="grid items-start gap-4 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
              <div className="flex flex-col gap-4">
                <Card title="Aktif uyarılar">
                  <EventList events={data.active_events} onShowMetric={showMetric} />
                </Card>
                <BriefingCard astronautId={data.astronaut.id} />
              </div>
              <Card title="Bu günün ölçümleri">
                <ReadingsTable latest={data.latest} systems={data.systems} selectedMetric={metric} onShowMetric={showMetric} />
              </Card>
            </section>

            <div className="grid items-start gap-4 lg:grid-cols-3">
              {/* scroll-mt: "Grafikte göster" kaydırınca panel sabit header'ın altında kalmasın */}
              <div id="metric-panel" className="scroll-mt-40 lg:col-span-2">
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
              <div className="scroll-mt-40">
                <ChatPanel astronautId={data.astronaut.id} />
              </div>
            </div>
          </div>
        );
      }}
    </QueryState>
  );
}
