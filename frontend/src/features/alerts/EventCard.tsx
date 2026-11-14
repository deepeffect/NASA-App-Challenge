/**
 * Olay kartı.
 *  severity → renk + rozet (info olaylar burada gösterilmez, sadece brifingde)
 *  source   → "Kural / Model tespiti / Tahmin"
 *  score    → "Güven: düşük / orta / yüksek"
 *  contributors → katkı çubukları
 *  butonlar: Neden? · Yanlış alarm · Yer ekibiyle paylaş
 */
import { useState } from "react";

import type { HealthEvent } from "../../api/client";
import { useExplain, useFeedback, useShare } from "../../api/queries";
import { useAsOf } from "../../app/AsOfContext";
import { SeverityBadge, Tag } from "../../components/ui/Badges";
import { fmtDate } from "../../components/ui/format";
import { confidenceLabel, SOURCE_LABELS, SYSTEM_LABELS } from "../../components/ui/labels";
import { Button, ErrorBox, Spinner } from "../../components/ui/primitives";
import { ContributorBars } from "./ContributorBars";
import { ExplainPanel } from "./ExplainPanel";

const BORDER = {
  critical: "border-l-red-500",
  warning: "border-l-orange-400",
  info: "border-l-sky-400",
};

export function EventCard({ event, onShowMetric }: { event: HealthEvent; onShowMetric?: (metric: string) => void }) {
  const { asOf } = useAsOf();
  const explain = useExplain();
  const feedback = useFeedback();
  const share = useShare();
  const [showExplain, setShowExplain] = useState(false);

  const onExplain = () => {
    setShowExplain((v) => !v);
    if (!explain.data && !explain.isPending) explain.mutate({ eventId: event.event_id, body: { lang: "tr", as_of: asOf } });
  };

  const primaryMetric = event.contributors[0]?.metric;

  return (
    <article className={`scroll-mt-40 space-y-4 rounded-2xl border border-l-8 border-slate-800 bg-slate-900/80 p-5 ${BORDER[event.severity]}`}>
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge severity={event.severity} />
          <Tag tone={event.source === "rule" ? "slate" : "violet"}>{SOURCE_LABELS[event.source]}</Tag>
          <Tag>Güven: {confidenceLabel(event.score)}</Tag>
          <Tag>{SYSTEM_LABELS[event.system]}</Tag>
          {event.status === "resolved" && <Tag>Sona erdi</Tag>}
        </div>
        <h3 className="text-xl font-semibold">{event.title}</h3>
        {event.description && <p className="text-slate-300">{event.description}</p>}
        <p className="text-sm text-slate-400">
          {fmtDate(event.window.start)} – {fmtDate(event.window.end)}
          {event.changepoint_date && <> · değişim noktası {fmtDate(event.changepoint_date)}</>}
        </p>
      </header>

      <ContributorBars contributors={event.contributors} />

      <div className="flex flex-wrap gap-2">
        <Button variant="primary" onClick={onExplain} aria-expanded={showExplain}>
          Neden?
        </Button>
        <Button
          onClick={() => feedback.mutate({ eventId: event.event_id, body: { verdict: "false_alarm" } })}
          disabled={feedback.isPending || event.feedback === "false_alarm"}
        >
          {event.feedback === "false_alarm" ? "Yanlış alarm olarak işaretlendi" : "Yanlış alarm"}
        </Button>
        <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-xl border border-slate-600 px-4 py-2">
          <input
            type="checkbox"
            className="h-5 w-5 accent-sky-400"
            checked={event.share_with_ground}
            disabled={share.isPending}
            onChange={(e) => share.mutate({ eventId: event.event_id, share: e.target.checked })}
          />
          Yer ekibiyle paylaş
        </label>
        {onShowMetric && primaryMetric && (
          <Button variant="ghost" onClick={() => onShowMetric(primaryMetric)}>
            Grafikte göster
          </Button>
        )}
      </div>
      {(feedback.isError || share.isError) && <ErrorBox error={feedback.error ?? share.error} />}

      {showExplain && (
        <div>
          {explain.isPending && <Spinner label="Açıklama hazırlanıyor…" />}
          {explain.isError && <ErrorBox error={explain.error} />}
          {explain.data && <ExplainPanel data={explain.data} />}
        </div>
      )}
    </article>
  );
}
