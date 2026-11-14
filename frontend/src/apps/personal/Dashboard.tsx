/**
 * Girişten sonraki ekran. Prototipteki sıra: durum + 30 günlük şerit → yapılacaklar → günlük check-in →
 * "bu günün ayrıntıları" (kapalı). Ek: en altta kapalı "Asistana sor" kartı.
 *
 * Değerlendirme burada yapılmaz: seçili günün `DayView`'ı backend'den gelir ve ortak bileşenlerle gösterilir.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { type PersonalCatalog, type PersonalOverview, StationApiError, stationApi } from "../../api/station";
import { ReadingsTable, ScoreChart, StatusCard, TodoCard, WhoRow } from "../../shared/health";
import { AskAssistant } from "./AskAssistant";
import { dropOtherLanguages, isUnauthorized, qk, useDay } from "./api";
import { CheckinCard } from "./CheckinCard";
import { useT } from "./texts";

export interface DashboardProps {
  overview: PersonalOverview;
  catalog: PersonalCatalog | undefined;
  onUnauthorized: (message: string) => void;
}

export function Dashboard({ overview, catalog, onUnauthorized }: DashboardProps) {
  const { t, lang } = useT();
  const qc = useQueryClient();
  const today = overview.today;
  // Gün seçimi: başlangıçta bugün (son kayıt). Şeritten, önceki/sonraki düğmelerinden veya grafikten değişir.
  const [day, setDay] = useState(today);
  const dayQuery = useDay(day, lang);
  // Yeni gün yüklenirken önceki günün görünümü ekranda kalır; başlık şeritten dolduğu için hemen doğrudur.
  const shown = dayQuery.data;
  const fresh = shown !== undefined && shown.day === day;

  // Komşu günler önceden istenir: önceki/sonraki geçişleri beklemesiz olsun.
  useEffect(() => {
    for (const d of [day - 1, day + 1]) {
      if (d >= 1 && d <= overview.n_days) void qc.prefetchQuery({ queryKey: qk.day(d, lang), queryFn: () => stationApi.day(d) });
    }
  }, [day, lang, overview.n_days, qc]);

  const [doneError, setDoneError] = useState<string | null>(null);
  const markDone = useMutation({
    mutationFn: ({ code, done }: { code: string; done: boolean }) => stationApi.actionDone(code, done),
    onMutate: () => setDoneError(null),
    onSuccess: (out) => {
      qc.setQueryData(qk.day(out.day.day, lang), out.day);
      dropOtherLanguages(qc, qk.dayAny(out.day.day), lang);
    },
    onError: (e) => {
      if (!isUnauthorized(e)) setDoneError(e instanceof StationApiError ? e.message : t("loadError"));
    },
  });

  return (
    <div className="appstack">
      <StatusCard
        audience="astronaut"
        strip={overview.strip}
        selectedDay={day}
        onSelectDay={setDay}
        view={fresh ? shown : null}
        statusLabels={catalog?.statuses}
      />

      {shown ? (
        <div aria-busy={!fresh}>
          <TodoCard
            audience="astronaut"
            view={shown}
            onToggleDone={(code, done) => markDone.mutate({ code, done })}
            busyCode={markDone.isPending ? markDone.variables.code : null}
          />
        </div>
      ) : dayQuery.isError ? (
        <p className="err" role="alert">
          {t("loadError")}
          <button type="button" onClick={() => void dayQuery.refetch()}>
            {t("retry")}
          </button>
        </p>
      ) : (
        <section className="card todo">
          <p className="waiting">{t("loading")}</p>
        </section>
      )}
      {doneError ? (
        <p className="err" role="alert">
          {doneError}
        </p>
      ) : null}

      <CheckinCard day={day} />

      <details className="card more">
        <summary>{t("detailsTitle")}</summary>
        <div className="stack">
          <WhoRow audience="astronaut" astronaut={overview.astronaut} />
          <ScoreChart audience="astronaut" points={overview.strip} selectedDay={day} onSelectDay={setDay} />
          {shown && catalog ? (
            <div aria-busy={!fresh}>
              <ReadingsTable audience="astronaut" view={shown} domains={catalog.domains} />
            </div>
          ) : (
            <p className="waiting">{t("loading")}</p>
          )}
        </div>
      </details>

      <AskAssistant onUnauthorized={onUnauthorized} />
    </div>
  );
}
