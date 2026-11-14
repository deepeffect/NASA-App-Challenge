import { useCrew } from "../../api/queries";
import { useAsOf } from "../../app/AsOfContext";
import { QueryState } from "../../components/ui/primitives";
import { CrewCard } from "./CrewCard";

export function CrewPage() {
  const { asOf } = useAsOf();
  const crew = useCrew(asOf);

  return (
    <QueryState query={crew} loadingLabel="Loading crew…">
      {(data) => (
        <div className="space-y-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h1 className="text-3xl font-bold">Crew</h1>
            <p className="text-slate-400">
              Mission day {data.mission.mission_day} · {data.astronauts.length} astronauts
            </p>
          </div>
          <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
            {data.astronauts.map((m) => (
              <CrewCard key={m.id} member={m} />
            ))}
          </div>
        </div>
      )}
    </QueryState>
  );
}
