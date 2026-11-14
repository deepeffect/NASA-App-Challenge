/** Global zaman kaydırıcısı: seçilen gün `as_of` olarak bütün sorgulara geçer. */
import { useEffect, useState } from "react";

import { useCrew } from "../api/queries";
import { ClockIcon } from "../components/ui/icons";
import { addDays, fmtDate } from "../components/ui/format";
import { Button } from "../components/ui/primitives";
import { useAsOf } from "./AsOfContext";

export function TimeSlider() {
  const { asOf, setAsOf } = useAsOf();
  const crew = useCrew(asOf);
  const mission = crew.data?.mission;
  const total = mission?.total_days ?? 0;
  const currentDay = mission?.mission_day ?? total;
  const [draft, setDraft] = useState<number | null>(null);

  // Sürüklerken her adımda istek atmamak için 300 ms debounce
  useEffect(() => {
    if (draft === null || !mission?.start_date) return;
    const t = setTimeout(() => {
      setAsOf(draft >= total ? null : addDays(mission.start_date!, draft - 1));
      setDraft(null);
    }, 300);
    return () => clearTimeout(t);
  }, [draft, mission?.start_date, total, setAsOf]);

  if (!mission?.start_date || !total) return null;
  const shownDay = draft ?? currentDay;
  const shownDate = addDays(mission.start_date, shownDay - 1);
  const live = asOf === null && draft === null;

  return (
    <div className="flex flex-wrap items-center gap-4">
      <label htmlFor="as-of" className="flex items-center gap-2 whitespace-nowrap text-slate-300">
        <ClockIcon />
        <span>
          Mission day <strong className="text-slate-100">{shownDay}</strong> / {total} · {fmtDate(shownDate)}
        </span>
      </label>
      <input
        id="as-of"
        type="range"
        min={1}
        max={total}
        value={shownDay}
        onChange={(e) => setDraft(Number(e.target.value))}
        className="h-2 min-w-48 flex-1 cursor-pointer"
        aria-valuetext={`Mission day ${shownDay}, ${fmtDate(shownDate)}`}
      />
      {live ? (
        <span className="rounded-full border border-emerald-600/70 px-3 py-1 text-sm text-emerald-300">● Live</span>
      ) : (
        <Button variant="secondary" onClick={() => { setDraft(null); setAsOf(null); }}>
          Back to live
        </Button>
      )}
    </div>
  );
}
