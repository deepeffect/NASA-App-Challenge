/**
 * Astronot ekranı (gemi, /me). Görünüm ve davranış için tek doğru kaynak:
 * frontend/reference/personal-artifact.html (astronot rolü) — düzen, metinler, "sorun yoksa sakin" renk
 * kullanımı, açık/koyu tema ve tek dar kolon aynen korunur (ortak bileşenler: src/shared/health).
 *
 * Prototipten farklar:
 *  - Veri sayfaya gömülü değildir; tipli istemciyle API'den gelir (src/api/station.ts) ve hiçbir kural
 *    arayüzde yeniden hesaplanmaz.
 *  - Giriş `POST /api/auth/login`; token sekme oturumunda (sessionStorage); "Çıkış" token'ı ve bu astronota
 *    ait her şeyi siler. Bu ekranda EARTH girişi yoktur.
 *  - Check-in ve paylaşım backend'de tutulur; check-in sadece bugün yapılır.
 *  - Üst barda TR/EN seçimi; yazı tipleri paketten gelir (offline).
 * Ekler: to-do'da "Yaptım", kapalı "Asistana sor" kartı, acil belirtide "sağlık sorumlusu bilgilendirildi" kutusu.
 *
 * Oturum yalıtımı (ortak ekran, birden çok astronot): giriş yapan astronota ait her şey — sorgular, yazma
 * istekleri, "yenisi gelene kadar eskisini göster" verisi — o oturuma özel bir sorgu istemcisinde yaşar ve
 * çıkışta istemciyle birlikte atılır (bkz. `newSessionClient`). Herkese açık veriler (kimlik ipucu, katalog)
 * uygulamanın istemcisinde kalır.
 */
import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useCallback, useEffect, useState } from "react";

import { auth, type PersonalCatalog, type StationInfo, StationApiError, stationApi } from "../../api/station";
import { HealthRoot, SelfCareDialog } from "../../shared/health";
import { isUnauthorized, useCatalog, useHint, useOverview } from "./api";
import { Dashboard } from "./Dashboard";
import { Login } from "./Login";
import "./personal.css";
import { useT } from "./texts";
import { TopBar } from "./TopBar";

/**
 * Her girişte yeni bir sorgu istemcisi (ayarlar uygulamanın istemcisinden alınır). Astronot değişince önceki
 * oturumdan kalan hiçbir şey sonraki astronotun ekranına ulaşamaz: ne yeni veri gelene kadar gösterilen eski
 * veri, ne de çıkıştan SONRA dönen geç bir cevap (yavaş model) — ikisi de atılmış istemciye yazılır.
 * Tek bir ortak önbellekte bunu anahtar silerek sağlamak yetmez: gözlemci silinen veriyi "önceki veri" olarak
 * hatırlar ve yoldaki yazma isteklerinin cevabı çıkıştan sonra önbelleğe geri yazılır.
 */
const newSessionClient = (app: QueryClient): QueryClient => new QueryClient({ defaultOptions: { ...app.getDefaultOptions() } });

/** Çerçeve: üst bar + içerik + "tüm öz bakım çözümleri" penceresi + dipnot. Giriş kartında da girişten sonra da aynı. */
type Frame = (who: string | null, days: number | undefined, content: ReactNode) => ReactNode;

export function PersonalApp(_props: { station: StationInfo }) {
  const { t, lang } = useT();
  const appClient = useQueryClient();
  const [session, setSession] = useState<QueryClient | null>(() => (auth.token !== null ? newSessionClient(appClient) : null));
  const [notice, setNotice] = useState<string | null>(null);
  const [infoOpen, setInfoOpen] = useState(false);

  // Herkese açık veriler: oturumdan bağımsızdır, uygulamanın istemcisinde kalır.
  const hint = useHint(lang);
  const catalog = useCatalog(lang);
  const count = hint.data?.astronauts?.count;

  /** Çıkış veya oturumun bitmesi: token silinir, oturumun istemcisi atılır, giriş kartına dönülür. */
  const endSession = useCallback(
    (message: string | null) => {
      stationApi.logout();
      session?.clear();
      setSession(null);
      setNotice(message);
    },
    [session],
  );

  const frame: Frame = (who, days, content) => (
    <>
      <TopBar who={who} authed={session !== null} onLogout={() => endSession(null)} onInfo={() => setInfoOpen(true)} />
      {content}
      <SelfCareDialog audience="astronaut" open={infoOpen} onClose={() => setInfoOpen(false)} solutions={catalog.data?.solutions ?? []} />
      <p className="muted">{count && days ? t("footnote", { count, days }) : t("footnoteShort")}</p>
    </>
  );

  return (
    <HealthRoot>
      {session ? (
        <QueryClientProvider client={session}>
          <Session catalog={catalog.data} onEnd={endSession} frame={frame} />
        </QueryClientProvider>
      ) : (
        frame(
          null,
          undefined,
          <Login
            notice={notice}
            onDone={() => {
              setNotice(null);
              setSession(newSessionClient(appClient));
            }}
          />,
        )
      )}
    </HealthRoot>
  );
}

interface SessionProps {
  catalog: PersonalCatalog | undefined;
  /** Çıkış (mesaj yok) veya oturumun bitmesi (giriş kartında gösterilecek mesajla). */
  onEnd: (message: string | null) => void;
  frame: Frame;
}

/** Giriş yapılmış ekran. Bu oturumun sorgu istemcisi altında çalışır; çıkışta tümüyle sökülür. */
function Session({ catalog, onEnd, frame }: SessionProps) {
  const { t, lang } = useT();
  const qc = useQueryClient(); // bu oturumun istemcisi
  const overview = useOverview(lang);

  // Herhangi bir sorgu veya değişiklik 401 dönerse (token süresi dolmuş, istasyon sıfırlanmış) girişe dön.
  useEffect(() => {
    const onError = (error: unknown) => {
      if (isUnauthorized(error)) onEnd((error as StationApiError).message || t("sessionEnded"));
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
  }, [qc, onEnd, t]);

  const me = overview.data;
  return frame(
    me ? `${me.astronaut.id} · ${me.astronaut.mission_label}` : null,
    me?.n_days,
    me ? (
      <Dashboard key={me.astronaut.id} overview={me} catalog={catalog} onUnauthorized={onEnd} />
    ) : overview.isError ? (
      <p className="err" role="alert">
        {t("loadError")}
        <button type="button" onClick={() => void overview.refetch()}>
          {t("retry")}
        </button>
      </p>
    ) : (
      <p className="waiting">{t("loading")}</p>
    ),
  );
}
