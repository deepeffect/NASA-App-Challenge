/**
 * Dünya üssü ekranı (/monitor). Tamamen salt okunur: bütün veri bu istasyonun backend'inden (earth.db)
 * okunur — gemiden downlink ile gelmiş, gemide gizlilik filtresinden geçmiş veri. Gemiye doğrudan istek yok.
 *
 * Kurallar ve görünüm için tek doğru kaynak: frontend/reference/personal-artifact.html (Earth görünümü).
 * Ayarlar (ürün adı, DEMO_CREW): ./config.ts · metinler: ./texts.ts · veri: ./api.ts · canlı akış: ./live.tsx
 */
import "@fontsource/archivo/600.css";
import "@fontsource/archivo/700.css";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "./monitor.css";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { auth, type StationInfo, stationApi } from "../../api/station";
import { isUnauthorized } from "./api";
import { LinkBar } from "./LinkBar";
import { LiveProvider } from "./live";
import { Login } from "./Login";
import { Footer, Header } from "./Shell";
import { useTheme } from "./ui";

export function MonitorApp({ station }: { station: StationInfo }) {
  const [theme, setTheme] = useTheme();
  const [authed, setAuthed] = useState(() => !!auth.token);
  const qc = useQueryClient();

  // Token geçersizse (süresi doldu, istasyon sıfırlandı) giriş ekranına dön
  useEffect(() => {
    return qc.getQueryCache().subscribe((e) => {
      if (e.type === "updated" && e.action.type === "error" && isUnauthorized(e.action.error)) setAuthed(false);
    });
  }, [qc]);

  function logout() {
    stationApi.logout();
    qc.removeQueries({ queryKey: ["monitor"] });
    setAuthed(false);
  }

  return (
    <div className="mon" data-theme={theme}>
      {authed ? (
        <LiveProvider>
          <Dashboard station={station} theme={theme} setTheme={setTheme} onLogout={logout} />
        </LiveProvider>
      ) : (
        <>
          <Login onDone={() => setAuthed(true)} />
          <Footer station={station} />
        </>
      )}
    </div>
  );
}

function Dashboard({ station, theme, setTheme, onLogout }: { station: StationInfo; theme: ReturnType<typeof useTheme>[0]; setTheme: ReturnType<typeof useTheme>[1]; onLogout: () => void }) {
  const topRef = useRef<HTMLDivElement>(null);
  // Sağ panel yapışkan başlığın altında kalsın: başlık yüksekliği CSS değişkeni olarak
  useLayoutEffect(() => {
    const el = topRef.current;
    if (!el) return;
    const set = () => el.parentElement?.style.setProperty("--top-h", `${Math.ceil(el.getBoundingClientRect().height) + 16}px`);
    set();
    const ro = new ResizeObserver(set);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <>
      <div className="mon-top" ref={topRef}>
        <Header theme={theme} setTheme={setTheme} onLogout={onLogout} />
        <LinkBar />
      </div>
      <div className="mon-body">
        <main className="mon-main" />
        <aside className="mon-side" />
      </div>
      <Footer station={station} />
    </>
  );
}
