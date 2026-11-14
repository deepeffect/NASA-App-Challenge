/** Günlük rapor (GET /daily_report → "report"). Aynı gün tekrar üretilmez; "Regenerate" force=true gönderir. */
import { Button, Card, ErrorBox } from "../../components/ui/primitives";
import { type AssistantSelection, useDailyReport, useRegenerateReport } from "./api";
import { SourceList, SourceText } from "./SourceText";
import { SelectionPending, Waiting } from "./Waiting";

export function DailyReportCard({ sel }: { sel: AssistantSelection }) {
  const q = useDailyReport(sel);
  const regen = useRegenerateReport(sel);
  const busy = !sel.ready || q.isFetching || regen.isPending;
  return (
    <Card
      title="Daily report"
      actions={
        <Button variant="ghost" className="text-sm" onClick={() => regen.mutate()} disabled={busy}>
          Regenerate
        </Button>
      }
    >
      {!sel.ready ? (
        <SelectionPending status={sel.status} message={sel.message} astronautId={sel.astronautId} day={sel.day} />
      ) : q.isPending || regen.isPending ? (
        <Waiting label="Preparing report…" />
      ) : q.isError ? (
        <ErrorBox error={q.error} />
      ) : (
        <div className="space-y-3">
          <SourceText text={q.data.report} sources={q.data.sources} />
          <SourceList text={q.data.report} sources={q.data.sources} />
          {regen.isError && <ErrorBox error={regen.error} />}
        </div>
      )}
    </Card>
  );
}
