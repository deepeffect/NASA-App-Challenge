import { NavLink, Outlet } from "react-router";

import { SatelliteIcon } from "../components/ui/icons";
import { HealthIndicator } from "./HealthIndicator";
import { TimeSlider } from "./TimeSlider";

const navCls = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-2 ${isActive ? "bg-slate-800 text-slate-50" : "text-slate-300 hover:bg-slate-800/60"}`;

export function Layout() {
  return (
    <div className="min-h-screen">
      {/* Telefonda header uzun (menü + kaydırıcı): sadece geniş ekranda sabitlenir */}
      <header className="z-20 border-b border-slate-800 bg-slate-950/95 backdrop-blur md:sticky md:top-0">
        <div className="mx-auto max-w-6xl space-y-3 px-5 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <SatelliteIcon className="h-7 w-7 text-sky-400" />
              <span className="font-[family-name:var(--font-display)] text-xl font-bold tracking-tight">Astronot Sağlık İzleme</span>
            </div>
            <nav className="flex items-center gap-1" aria-label="Ana menü">
              <NavLink to="/" end className={navCls}>
                Mürettebat
              </NavLink>
              <NavLink to="/checkin" className={navCls}>
                Check-in
              </NavLink>
            </nav>
            <HealthIndicator />
          </div>
          <TimeSlider />
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-5 pb-6 pt-7">
        <Outlet />
      </main>
      <footer className="mx-auto max-w-6xl px-5 pb-12">
        <p className="max-w-[80ch] text-[13px] text-slate-400">
          Veriler sentetiktir. Eşikler ve normal aralıklar doğrulanmamış yer tutuculardır (NASA-STD-3001 ile
          doğrulanacak). Bu sistem karar desteği verir, teşhis koymaz; ciddi belirtide acil protokolü ve görev hekimi
          / yer ekibi esastır.
        </p>
      </footer>
    </div>
  );
}
