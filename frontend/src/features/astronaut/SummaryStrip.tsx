/** Özet şeridi: durum · genel skor · aktif uyarılar · ana endişe. Tüm sayılar API'den gelir. */
import type { ReactNode } from "react";

import type { AstronautSummary, ScoreHistoryResponse } from "../../api/client";
import { StatusBadge } from "../../components/ui/Badges";
import { fmtNum } from "../../components/ui/format";
import { SYSTEM_LABELS } from "../../components/ui/labels";

function Tile({ eyebrow, children, sub }: { eyebrow: string; children: ReactNode; sub: ReactNode }) {
  return (
    <div className="flex flex-col gap-1 rounded-2xl border border-slate-800 bg-slate-900 px-4 py-3.5">
      <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">{eyebrow}</span>
      <span className="font-[family-name:var(--font-display)] text-3xl font-bold leading-tight">{children}</span>
      <span className="text-sm text-slate-300">{sub}</span>
    </div>
  );
}

export function SummaryStrip({ data, bands }: { data: AstronautSummary; bands?: ScoreHistoryResponse["bands"] }) {
  const shown = data.active_events.filter((e) => e.severity !== "info");
  const critical = shown.filter((e) => e.severity === "critical").length;
  const warning = shown.length - critical;
  const attention = data.systems.filter((s) => s.status === "yellow" || s.status === "red").length;
  const worst = data.overall.worst_system;

  return (
    <section className="grid grid-cols-1 gap-3 min-[421px]:grid-cols-2 lg:grid-cols-4" aria-live="polite">
      <Tile eyebrow="Durum" sub="en zayıf sistemin durumu">
        <StatusBadge status={data.overall.status} size="lg" />
      </Tile>
      <Tile
        eyebrow="Genel skor"
        sub={
          bands
            ? `normal ${fmtNum(bands.green_min, 0)}+ · kritik ${fmtNum(bands.yellow_min, 0)} altı`
            : "en zayıf sistemin skoru"
        }
      >
        <span className="num">{fmtNum(data.overall.score, 0)}</span>
        <span className="text-base font-normal text-slate-400"> / 100</span>
      </Tile>
      <Tile eyebrow="Aktif uyarı" sub={shown.length ? `${critical} kritik · ${warning} uyarı` : "bu gün için uyarı yok"}>
        <span className="num">{shown.length}</span>
      </Tile>
      <Tile
        eyebrow="Ana endişe"
        sub={attention ? `${attention} sistem dikkat gerektiriyor` : "tüm sistemler normal"}
      >
        <span className="text-2xl">{worst ? SYSTEM_LABELS[worst] : "Yok"}</span>
      </Tile>
    </section>
  );
}
