import { useState, type FormEvent } from "react";

import type { CheckinResponse } from "../../api/client";
import { useSubmitCheckin } from "../../api/queries";
import { EmergencyBanner } from "../../components/ui/EmergencyBanner";
import { CheckCircleIcon } from "../../components/ui/icons";
import { Button, ErrorBox } from "../../components/ui/primitives";

type ScaleKey = "mood" | "stress" | "sleep_quality";

const SCALES: { key: ScaleKey; label: string; low: string; high: string }[] = [
  { key: "mood", label: "Your mood", low: "Very bad", high: "Very good" },
  { key: "stress", label: "Your stress level", low: "Very low", high: "Very high" },
  { key: "sleep_quality", label: "Your sleep quality", low: "Very bad", high: "Very good" },
];

export function CheckinForm({ astronautId }: { astronautId: string }) {
  const submit = useSubmitCheckin();
  const [values, setValues] = useState<Record<ScaleKey, number | null>>({ mood: null, stress: null, sleep_quality: null });
  const [note, setNote] = useState("");
  const [share, setShare] = useState(false);
  const [result, setResult] = useState<CheckinResponse | null>(null);

  const complete = SCALES.every((s) => values[s.key] !== null);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!complete) return;
    submit.mutate(
      {
        astronaut_id: astronautId,
        mood: values.mood!,
        stress: values.stress!,
        sleep_quality: values.sleep_quality!,
        note: note.trim() || null,
        share_with_ground: share,
        lang: "en",
      },
      { onSuccess: setResult },
    );
  };

  if (result) {
    return (
      <div className="space-y-4">
        {result.emergency && <EmergencyBanner notice={result.emergency} />}
        <p className="flex items-center gap-2 text-lg text-emerald-300">
          <CheckCircleIcon /> Check-in saved.
        </p>
        <Button
          onClick={() => {
            setResult(null);
            setValues({ mood: null, stress: null, sleep_quality: null });
            setNote("");
            setShare(false);
          }}
        >
          New check-in
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-6">
      {SCALES.map((s) => (
        <fieldset key={s.key} className="space-y-2">
          <legend className="text-lg font-semibold">{s.label}</legend>
          <div className="flex flex-wrap items-center gap-2">
            <span className="w-24 text-sm text-slate-400">{s.low}</span>
            {[1, 2, 3, 4, 5].map((n) => {
              const selected = values[s.key] === n;
              return (
                <label
                  key={n}
                  className={`relative flex h-14 w-14 cursor-pointer items-center justify-center rounded-xl border text-xl font-semibold has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-sky-400 ${
                    selected
                      ? "border-white bg-sky-500 text-slate-950 ring-2 ring-white ring-offset-2 ring-offset-slate-900"
                      : "border-slate-600 bg-slate-800 hover:bg-slate-700"
                  }`}
                >
                  {/* Seçim sadece renkle anlatılmaz: köşede onay işareti + çerçeve */}
                  {selected && (
                    <span className="absolute -right-2 -top-2 rounded-full bg-white text-slate-950" aria-hidden>
                      <CheckCircleIcon className="h-5 w-5" />
                    </span>
                  )}
                  <input
                    type="radio"
                    name={s.key}
                    value={n}
                    checked={selected}
                    onChange={() => setValues((v) => ({ ...v, [s.key]: n }))}
                    className="sr-only"
                  />
                  {n}
                </label>
              );
            })}
            <span className="w-24 text-sm text-slate-400">{s.high}</span>
          </div>
        </fieldset>
      ))}

      <div className="space-y-2">
        <label htmlFor="note" className="text-lg font-semibold">
          Note (optional)
        </label>
        <textarea
          id="note"
          rows={4}
          maxLength={2000}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          className="w-full rounded-xl border border-slate-600 bg-slate-950 p-3"
          placeholder="How are you feeling today?"
        />
        <p className="text-sm text-slate-500">The note is automatically scanned for emergency symptoms (independent of the AI).</p>
      </div>

      <label className="flex cursor-pointer items-center gap-3">
        <input type="checkbox" checked={share} onChange={(e) => setShare(e.target.checked)} className="h-6 w-6 accent-sky-400" />
        <span className="text-lg">Share with ground team</span>
      </label>

      {submit.isError && <ErrorBox error={submit.error} />}
      <div className="flex flex-wrap items-center gap-4">
        <Button variant="primary" type="submit" disabled={!complete || submit.isPending} className="text-lg">
          {submit.isPending ? "Saving…" : "Save"}
        </Button>
        {!complete && (
          <p className="text-slate-400">
            Select all three scales to save ({SCALES.filter((s) => values[s.key] !== null).length}/3).
          </p>
        )}
      </div>
    </form>
  );
}
