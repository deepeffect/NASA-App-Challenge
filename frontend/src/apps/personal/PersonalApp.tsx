/**
 * Astronot ekranı (gemi, /me). Görünüm ve davranış için tek doğru kaynak:
 * frontend/reference/personal-artifact.html (astronot rolü) — düzen, metinler, "sorun yoksa sakin" renk
 * kullanımı, açık/koyu tema ve tek dar kolon aynen korunur (ortak bileşenler: src/shared/health).
 *
 * Prototipten farklar:
 *  - Veri sayfaya gömülü değildir; tipli istemciyle API'den gelir (src/api/station.ts) ve hiçbir kural
 *    arayüzde yeniden hesaplanmaz.
 *  - Giriş `POST /api/auth/login`; token sekme oturumunda (sessionStorage); "Çıkış" token'ı ve bu astronota
 *    ait önbelleği siler. Bu ekranda EARTH girişi yoktur.
 *  - Check-in ve paylaşım backend'de tutulur; check-in sadece bugün yapılır.
 *  - Üst barda TR/EN seçimi; yazı tipleri paketten gelir (offline).
 * Ekler: to-do'da "Yaptım", kapalı "Asistana sor" kartı, acil belirtide "sağlık sorumlusu bilgilendirildi" kutusu.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";

import { auth, type StationInfo, StationApiError, stationApi } from "../../api/station";
import { HealthRoot, SelfCareDialog } from "../../shared/health";
import { clearPersonalData, isUnauthorized, useCatalog, useHint, useOverview } from "./api";
import { Dashboard } from "./Dashboard";
import { Login } from "./Login";
import "./personal.css";
import { useT } from "./texts";
import { TopBar } from "./TopBar";

export function PersonalApp(_props: { station: StationInfo }) {
  const { t, lang } = useT();
  const qc = useQueryClient();
  const [authed, setAuthed] = useState(() => auth.token !== null);
  const [notice, setNotice] = useState<string | null>(null);
  const [infoOpen, setInfoOpen] = useState(false);

  const hint = useHint(lang);
  const catalog = useCatalog(lang);
  const overview = useOverview(lang, authed);

  /** Çıkış veya oturumun bitmesi: token ve bu astronota ait bütün önbellek silinir, giriş kartına dönülür. */
  const endSession = useCallback(
    (message: string | null) => {
      stationApi.logout();
      clearPersonalData(qc);
      setAuthed(false);
      setNotice(message);
    },
    [qc],
  );

  // Herhangi bir sorgu veya değişiklik 401 dönerse (token süresi dolmuş, istasyon sıfırlanmış) girişe dön.
  useEffect(() => {
    const onError = (error: unknown) => {
      if (isUnauthorized(error)) endSession((error as StationApiError).message || t("sessionEnded"));
    };
    const offQueries = qc.getQueryCache().subscribe((e) => {
      if (e.type === "updated" && e.action.type === "error") onError(e.action.error);
    });
    const offMutations = qc.getMutationCache().subscribe((e) => {
      if (e.type === "updated" && e.action.type === "error") onError(e.action.error);
    });
    return () => {
      offQueries();
      offMutations();
    };
  }, [qc, endSession, t]);

  const astronaut = authed ? overview.data?.astronaut : undefined;
  const count = hint.data?.astronauts?.count;
  const days = overview.data?.n_days;

  return (
    <HealthRoot>
      <TopBar
        who={astronaut ? `${astronaut.id} · ${astronaut.mission_label}` : null}
        authed={authed}
        onLogout={() => endSession(null)}
        onInfo={() => setInfoOpen(true)}
      />

      {!authed ? (
        <Login
          notice={notice}
          onDone={() => {
            setNotice(null);
            setAuthed(true);
          }}
        />
      ) : overview.data ? (
        // key: başka bir astronot giriş yaparsa ekran (seçili gün, sohbet, açık bölümler) sıfırdan kurulur
        <Dashboard key={overview.data.astronaut.id} overview={overview.data} catalog={catalog.data} onUnauthorized={endSession} />
      ) : overview.isError ? (
        <p className="err" role="alert">
          {t("loadError")}
          <button type="button" onClick={() => void overview.refetch()}>
            {t("retry")}
          </button>
        </p>
      ) : (
        <p className="waiting">{t("loading")}</p>
      )}

      <SelfCareDialog audience="astronaut" open={infoOpen} onClose={() => setInfoOpen(false)} solutions={catalog.data?.solutions ?? []} />

      <p className="muted">{count && days ? t("footnote", { count, days }) : t("footnoteShort")}</p>
    </HealthRoot>
  );
}
