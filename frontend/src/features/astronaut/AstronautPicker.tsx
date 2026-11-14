/** Astronot seçici: açılır liste + Önceki / Sonraki. Seçili gün (as_of) gezinirken korunur. */
import { Link, useNavigate } from "react-router";

import { useCrew } from "../../api/queries";
import { useAsOf } from "../../app/AsOfContext";
import { STATUS_LABELS } from "../../components/ui/labels";
import { Button } from "../../components/ui/primitives";

export function AstronautPicker({ currentId }: { currentId: string }) {
  const { asOf } = useAsOf();
  const crew = useCrew(asOf);
  const navigate = useNavigate();
  const list = crew.data?.astronauts ?? [];
  const index = list.findIndex((a) => a.id === currentId);

  const go = (k: number) => {
    if (!list.length) return;
    const next = list[(k + list.length) % list.length];
    navigate(`/astronauts/${next.id}`);
  };

  return (
    <section
      aria-label="Astronot seç"
      className="flex flex-wrap items-end gap-2.5 rounded-2xl border border-slate-800 bg-slate-900 px-4 py-3.5"
    >
      <div className="flex min-w-0 flex-[1_1_260px] flex-col gap-1">
        <label htmlFor="astronaut-select" className="text-xs font-semibold text-slate-400">
          Astronot
        </label>
        <select
          id="astronaut-select"
          value={currentId}
          onChange={(e) => navigate(`/astronauts/${e.target.value}`)}
          className="min-h-10 w-full rounded-xl border border-slate-600 bg-slate-900 px-2.5"
        >
          {index < 0 && <option value={currentId}>{currentId}</option>}
          {list.map((a) => (
            <option key={a.id} value={a.id}>
              {a.id} · {a.name}
              {a.role ? ` · ${a.role}` : ""} · {STATUS_LABELS[a.status]}
            </option>
          ))}
        </select>
      </div>
      <Button onClick={() => go(index - 1)} disabled={list.length < 2}>
        Önceki
      </Button>
      <Button onClick={() => go(index + 1)} disabled={list.length < 2}>
        Sonraki
      </Button>
      <Link
        to={`/checkin/${currentId}`}
        className="inline-flex min-h-11 items-center rounded-xl border border-slate-600 bg-slate-800 px-4 font-medium hover:bg-slate-700"
      >
        Günlük check-in
      </Link>
    </section>
  );
}
