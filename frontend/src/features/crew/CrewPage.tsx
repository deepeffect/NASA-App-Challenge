import { useCrew } from "../../api/queries";
import { useAsOf } from "../../app/AsOfContext";
import { QueryState } from "../../components/ui/primitives";
import { CrewCard } from "./CrewCard";

export function CrewPage() {
  const { asOf } = useAsOf();
  const crew = useCrew(asOf);

  return (
    <QueryState query={crew} loadingLabel="Mürettebat yükleniyor…">
      {(data) => (
        <div className="space-y-5">
          <header>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h1 className="text-[28px] font-bold leading-tight tracking-tight">Mürettebat</h1>
              <p className="text-slate-400">
                Görev günü {data.mission.mission_day} · {data.astronauts.length} astronot
              </p>
            </div>
            <p className="mt-1 max-w-[68ch] text-slate-300">
              Seçili gün için her astronotun genel durumu. Skorları, ölçümleri ve uyarıları görmek için bir astronot
              seçin.
            </p>
          </header>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {data.astronauts.map((m) => (
              <CrewCard key={m.id} member={m} />
            ))}
          </div>
        </div>
      )}
    </QueryState>
  );
}
