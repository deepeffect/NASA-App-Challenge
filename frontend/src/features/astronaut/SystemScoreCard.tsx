import type { ScoreDay, SystemScore } from "../../api/client";
import { Sparkline } from "../../components/charts/ScoreCharts";
import { StatusBadge } from "../../components/ui/Badges";
import { fmtNum } from "../../components/ui/format";

/** Sistem kartı: skor, durum rozeti, skor geçmişi mini grafiği ve skoru düşüren olaylar. */
export function SystemScoreCard({
  score,
  history,
  selectedDate,
  mainConcern,
}: {
  score: SystemScore;
  history?: ScoreDay[];
  selectedDate?: string | null;
  mainConcern?: boolean;
}) {
  const values = history?.map((d) => d.systems[score.system]) ?? [];
  const known = values.filter((v): v is number => v != null);
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 px-4 py-3.5">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-[15px] font-semibold">{score.display_name}</h3>
        <span className="num font-[family-name:var(--font-display)] text-2xl font-bold">{fmtNum(score.score, 0)}</span>
      </div>
      <div className="mt-1 flex min-h-6 flex-wrap items-center justify-between gap-2">
        <StatusBadge status={score.status} size="sm" />
        {mainConcern && <span className="text-xs font-semibold text-slate-300">Bu günün ana endişesi</span>}
      </div>
      {history && history.length > 1 && (
        <Sparkline
          values={values}
          selectedIndex={history.findIndex((d) => d.date === selectedDate)}
          label={
            known.length
              ? `${score.display_name} skoru, ${history.length} gün: ${fmtNum(known[0], 0)} → ${fmtNum(known[known.length - 1], 0)}`
              : `${score.display_name}: veri yok`
          }
        />
      )}
      {score.penalties.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm text-slate-400">
          {score.penalties.map((p) => (
            <li key={p.event_id} className="flex justify-between gap-2">
              <span className="truncate" title={p.title}>
                {p.title}
              </span>
              <span className="num shrink-0">−{fmtNum(p.penalty, 0)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
