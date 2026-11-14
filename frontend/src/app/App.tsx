/**
 * Kök router. Aynı derleme iki istasyonda servis edilir; her istasyon sadece kendi ekranını açar:
 *   /me       astronot ekranı (gemi)        → apps/personal
 *   /monitor  Dünya üssü ekranı (Dünya)     → apps/monitor
 *   /legacy   eski ekranlar (gemi + DATA_SOURCE=synthetic)
 *   /         bu istasyonun ana ekranına yönlendirir
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";

import { MonitorApp } from "../apps/monitor/MonitorApp";
import { PersonalApp } from "../apps/personal/PersonalApp";
import { LangProvider, useLang } from "../shared/i18n";
import { LegacyOnly, StationGate, StationOnly } from "../shared/station";
import { LegacyApp } from "./LegacyApp";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false },
  },
});

function NotFound() {
  const { t } = useLang();
  return <p className="mx-auto mt-24 max-w-lg px-4 text-center">{t("notFound")}</p>;
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <LangProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<StationGate>{(s) => <Navigate to={s.home_path} replace />}</StationGate>} />
            <Route
              path="/me/*"
              element={
                <StationOnly role="ship">
                  <StationGate>{(s) => <PersonalApp station={s} />}</StationGate>
                </StationOnly>
              }
            />
            <Route
              path="/monitor/*"
              element={
                <StationOnly role="earth">
                  <StationGate>{(s) => <MonitorApp station={s} />}</StationGate>
                </StationOnly>
              }
            />
            <Route
              path="/legacy/*"
              element={
                <LegacyOnly>
                  <LegacyApp />
                </LegacyOnly>
              }
            />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </LangProvider>
    </QueryClientProvider>
  );
}
