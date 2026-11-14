/**
 * Eski ekranlar (sentetik veri + eski analiz motoru). Sadece gemi + DATA_SOURCE=synthetic iken çalışır;
 * yeni mimaride /me (gemi) ve /monitor (Dünya) kullanılır. Rotalar /legacy altında.
 */
import { Route, Routes } from "react-router";

import { AstronautPage } from "../features/astronaut";
import { CheckinPage } from "../features/checkin";
import { CrewPage } from "../features/crew";
import { AsOfProvider } from "./AsOfContext";
import { Layout } from "./Layout";

export const LEGACY = "/legacy";

export function LegacyApp() {
  return (
    <AsOfProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<CrewPage />} />
          <Route path="astronauts/:id" element={<AstronautPage />} />
          <Route path="checkin" element={<CheckinPage />} />
          <Route path="checkin/:id" element={<CheckinPage />} />
          <Route path="*" element={<p>Sayfa bulunamadı.</p>} />
        </Route>
      </Routes>
    </AsOfProvider>
  );
}
