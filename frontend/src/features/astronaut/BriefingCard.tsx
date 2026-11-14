import { useBriefing } from "../../api/queries";
import { useAsOf } from "../../app/AsOfContext";
import { SeverityBadge, Tag } from "../../components/ui/Badges";
import { Card, QueryState } from "../../components/ui/primitives";

const GENERATED_BY = { llm: "Yapay zekâ", mock: "Mock", template_fallback: "Kural tabanlı şablon" };

/** Günlük brifing. info seviyesindeki olaylar SADECE burada gösterilir. */
export function BriefingCard({ astronautId }: { astronautId: string }) {
  const { asOf } = useAsOf();
  const briefing = useBriefing(astronautId, asOf);

  return (
    <Card title="Günlük brifing">
      <QueryState query={briefing} loadingLabel="Brifing hazırlanıyor…">
        {(data) => {
          const b = data.briefing;
          return (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2">
                <Tag tone="sky">{GENERATED_BY[data.generated_by]}</Tag>
                {data.cached && <Tag>önbellekten</Tag>}
              </div>
              <p className="text-lg">{b.summary}</p>
              {b.concerns.length > 0 && (
                <Section title="Dikkat edilecekler" items={b.concerns} />
              )}
              {b.recommended_actions.length > 0 && <Section title="Öneriler" items={b.recommended_actions} />}
              {b.highlights.length > 0 && <Section title="İyi gidenler" items={b.highlights} />}
              {data.info_events.length > 0 && (
                <div>
                  <p className="text-sm font-medium text-slate-400">Bilgi notları</p>
                  <ul className="mt-1 space-y-1">
                    {data.info_events.map((e) => (
                      <li key={e.event_id} className="flex items-start gap-2">
                        <SeverityBadge severity="info" />
                        <span>{e.title}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {b.escalate_to_ground && (
                <p className="rounded-lg border border-amber-500/60 bg-amber-950/50 px-3 py-2 text-amber-200">
                  Yer ekibine iletilmesi öneriliyor.
                </p>
              )}
              {b.uncertainty && <p className="text-sm text-slate-400">Belirsizlik: {b.uncertainty}</p>}
            </div>
          );
        }}
      </QueryState>
    </Card>
  );
}

function Section({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <p className="text-sm font-medium text-slate-400">{title}</p>
      <ul className="list-disc space-y-1 pl-6">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
