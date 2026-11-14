import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router";

import { AstronautPage } from "../features/astronaut";
import { CheckinPage } from "../features/checkin";
import { CrewPage } from "../features/crew";
import { AsOfProvider } from "./AsOfContext";
import { Layout } from "./Layout";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
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
      </BrowserRouter>
    </QueryClientProvider>
  );
}
