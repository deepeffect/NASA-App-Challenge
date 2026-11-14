/**
 * Asistan API'sinin uyarıları (GET /alerts). Önce kural tabanlı `fallback` metni (LLM çökse de dolu),
 * ardından LLM açıklaması. level RED → kırmızı bant. Durum her zaman ikon + metinle anlatılır.
 */
import { AlertTriangleIcon, OctagonAlertIcon } from "../../components/ui/icons";
import { Button, Card, ErrorBox } from "../../components/ui/primitives";
import { type AssistantAlert, type AssistantSelection, useAssistantAlerts } from "./api";
import { SourceList, SourceText } from "./SourceText";
import { SelectionPending, Waiting } from "./Waiting";

export function AssistantAlertsCard({ sel }: { sel: AssistantSelection }) {
  const q = useAssistantAlerts(sel);
  return (
    <Card
      title="Assistant alerts"
      actions={
        <Button variant="ghost" className="text-sm" onClick={() => void q.refetch()} disabled={!sel.ready || q.isFetching}>
          Refresh
        </Button>
      }
    >
      {!sel.ready ? (
        <SelectionPending status={sel.status} message={sel.message} astronautId={sel.astronautId} day={sel.day} />
      ) : q.isPending ? (
        <Waiting label="Loading alerts…" />
      ) : q.isError ? (
        <ErrorBox error={q.error} />
      ) : q.data.alerts.length === 0 ? (
        <p className="text-slate-400">No RED or YELLOW alerts.</p>
      ) : (
        <ul className="space-y-3">
          {q.data.alerts.map((a, i) => (
            <AlertItem key={`${a.tag ?? a.indicator}-${i}`} alert={a} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function AlertItem({ alert }: { alert: AssistantAlert }) {
  const red = alert.level.toUpperCase() === "RED";
  return (
    <li
      role={red ? "alert" : undefined}
      className={`space-y-2 rounded-xl p-4 ${
        red ? "border-2 border-red-500 bg-red-950/80 text-red-50" : "border border-amber-500/60 bg-amber-950/30"
      }`}
    >
      <p className={`flex items-center gap-2 font-semibold ${red ? "text-lg text-red-100" : "text-amber-200"}`}>
        {red ? <OctagonAlertIcon className="h-6 w-6 text-red-300" /> : <AlertTriangleIcon className="h-5 w-5" />}
        {red ? "Critical (RED)" : "Caution (YELLOW)"} — {alert.indicator}
      </p>
      <p>{alert.fallback}</p>
      {alert.explanation ? (
        <div className="space-y-2 border-t border-slate-700/70 pt-2">
          <p className="text-sm font-medium text-slate-400">AI explanation</p>
          <SourceText text={alert.explanation} sources={alert.sources} />
          <SourceList text={alert.explanation} sources={alert.sources} />
        </div>
      ) : (
        <p className="text-sm text-slate-400">AI explanation unavailable; the rule-based message above still applies.</p>
      )}
    </li>
  );
}
