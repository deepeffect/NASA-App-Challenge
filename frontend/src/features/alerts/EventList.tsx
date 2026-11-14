import type { HealthEvent } from "../../api/client";
import { CheckCircleIcon } from "../../components/ui/icons";
import { EventCard } from "./EventCard";

/** warning/critical olayları listeler; info olaylar sadece brifingde gösterilir. */
export function EventList({ events, onShowMetric }: { events: HealthEvent[]; onShowMetric?: (metric: string) => void }) {
  const visible = events.filter((e) => e.severity !== "info");
  if (!visible.length) {
    return (
      <p className="flex items-center gap-2 text-emerald-300">
        <CheckCircleIcon /> Aktif uyarı yok.
      </p>
    );
  }
  return (
    <div className="space-y-4">
      {visible.map((e) => (
        <EventCard key={e.event_id} event={e} onShowMetric={onShowMetric} />
      ))}
    </div>
  );
}
