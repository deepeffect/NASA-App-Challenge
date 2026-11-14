import type { SystemScore } from "../../api/client";
import { StatusBadge } from "../../components/ui/Badges";
import { fmtNum } from "../../components/ui/format";

export function SystemScoreCard({ score }: { score: SystemScore }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="font-semibold">{score.display_name}</p>
        <StatusBadge status={score.status} size="sm" />
      </div>
      <p className="mt-2 text-4xl font-bold tabular-nums">
        {fmtNum(score.score, 0)}
        <span className="text-lg font-normal text-slate-500"> / 100</span>
      </p>
      {score.penalties.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm text-slate-400">
          {score.penalties.map((p) => (
            <li key={p.event_id} className="flex justify-between gap-2">
              <span className="truncate" title={p.title}>{p.title}</span>
              <span className="shrink-0 tabular-nums">−{fmtNum(p.penalty, 0)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
