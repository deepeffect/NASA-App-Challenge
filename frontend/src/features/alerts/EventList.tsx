import { useState } from "react";

import type { HealthEvent } from "../../api/client";
import { CheckCircleIcon } from "../../components/ui/icons";
import { Button } from "../../components/ui/primitives";
import { EventCard } from "./EventCard";

const INITIAL = 3;

/**
 * warning/critical olayları listeler (en ciddi önce, backend sıralı gönderir).
 * Bilişsel yükü düşük tutmak için ilk 3 kart gösterilir; gerisi istenirse açılır.
 * info olaylar burada değil, sadece brifingde gösterilir.
 */
export function EventList({ events, onShowMetric }: { events: HealthEvent[]; onShowMetric?: (metric: string) => void }) {
  const [showAll, setShowAll] = useState(false);
  const visible = events.filter((e) => e.severity !== "info");
  if (!visible.length) {
    return (
      <p className="flex items-center gap-2 text-emerald-300">
        <CheckCircleIcon /> No active alerts.
      </p>
    );
  }
  const shown = showAll ? visible : visible.slice(0, INITIAL);
  const hidden = visible.length - shown.length;
  return (
    <div className="space-y-4">
      {shown.map((e) => (
        <EventCard key={e.event_id} event={e} onShowMetric={onShowMetric} />
      ))}
      {visible.length > INITIAL && (
        <Button variant="secondary" className="w-full" onClick={() => setShowAll((v) => !v)} aria-expanded={showAll}>
          {showAll ? "Show less" : `Show all alerts (${hidden} more)`}
        </Button>
      )}
    </div>
  );
}
