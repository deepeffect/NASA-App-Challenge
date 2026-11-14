import { useNavigate, useParams } from "react-router";

import { useCrew } from "../../api/queries";
import { useAsOf } from "../../app/AsOfContext";
import { Card } from "../../components/ui/primitives";
import { CheckinForm } from "./CheckinForm";

export function CheckinPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { asOf } = useAsOf();
  const crew = useCrew(asOf);

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <h1 className="text-3xl font-bold">Daily check-in</h1>
      <Card>
        <label htmlFor="astro" className="mb-2 block text-lg font-semibold">
          Astronaut
        </label>
        <select
          id="astro"
          value={id ?? ""}
          onChange={(e) => navigate(`/checkin/${e.target.value}`)}
          className="mb-6 min-h-11 w-full rounded-xl border border-slate-600 bg-slate-800 px-3"
        >
          <option value="" disabled>
            Select…
          </option>
          {crew.data?.astronauts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name} ({a.id})
            </option>
          ))}
        </select>
        {id ? <CheckinForm key={id} astronautId={id} /> : <p className="text-slate-400">Select an astronaut first.</p>}
      </Card>
    </div>
  );
}
