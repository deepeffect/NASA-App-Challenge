/** Günlük rapor (GET /daily_report → "report"). Aynı gün tekrar üretilmez; "Regenerate" force=true gönderir. */
import { Button, Card, ErrorBox } from "../../components/ui/primitives";
import { useDailyReport, useRegenerateReport } from "./api";
import { SourceList, SourceText } from "./SourceText";
import { Waiting } from "./Waiting";

export function DailyReportCard() {
  const q = useDailyReport();
  const regen = useRegenerateReport();
  const busy = q.isFetching || regen.isPending;
  return (
    <Card
      title="Daily report"
      actions={
        <Button variant="ghost" className="text-sm" onClick={() => regen.mutate()} disabled={busy}>
          Regenerate
        </Button>
      }
    >
      {q.isPending || regen.isPending ? (
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
