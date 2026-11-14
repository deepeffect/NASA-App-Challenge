/**
 * İstasyon bilgisi (GET /api/station) ve rol koruması: /me sadece gemide, /monitor sadece Dünya'da.
 * Diğer istasyonda "bu ekran bu istasyonda değil" gösterilir.
 */
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { type StationInfo, type StationRole, stationApi } from "../api/station";
import { useLang } from "./i18n";

export function useStation() {
  return useQuery({ queryKey: ["station"], queryFn: stationApi.station, staleTime: Infinity, retry: 2 });
}

function Center({ children }: { children: ReactNode }) {
  return <div className="mx-auto mt-24 max-w-lg space-y-3 px-4 text-center">{children}</div>;
}

export function StationGate({ children }: { children: (station: StationInfo) => ReactNode }) {
  const { data, isPending, isError } = useStation();
  const { t } = useLang();
  if (isPending) return <Center><p className="text-slate-400">{t("loading")}</p></Center>;
  if (isError || !data) return <Center><p role="alert">⚠ {t("backendDown")}</p></Center>;
  return <>{children(data)}</>;
}

export function NotOnStation({ station }: { station: StationInfo }) {
  const { t } = useLang();
  return (
    <Center>
      <h1 className="text-xl font-bold">{t("notOnStationTitle")}</h1>
      <p className="text-slate-300">
        {t("notOnStationText", { station: t(station.role) })}{" "}
        <Link className="text-sky-400 underline" to={station.home_path}>
          {station.home_path}
        </Link>
      </p>
    </Center>
  );
}

/** Sadece verilen roldeki istasyonda içeriği gösterir. */
export function StationOnly({ role, children }: { role: StationRole; children: ReactNode }) {
  return (
    <StationGate>
      {(station) =>
        station.role === role && !station.legacy_enabled ? children : <NotOnStation station={station} />
      }
    </StationGate>
  );
}

export function LegacyOnly({ children }: { children: ReactNode }) {
  const { t } = useLang();
  return (
    <StationGate>
      {(station) =>
        station.legacy_enabled ? (
          children
        ) : (
          <Center>
            <p>{t("legacyOff")}</p>
            <Link className="text-sky-400 underline" to={station.home_path}>
              {station.home_path}
            </Link>
          </Center>
        )
      }
    </StationGate>
  );
}
