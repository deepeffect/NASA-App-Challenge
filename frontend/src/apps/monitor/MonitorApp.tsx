/**
 * Dünya üssü ekranı (/monitor) — YER TUTUCU. Salt okunur; veri gemiden downlink ile gelir.
 * Kurallar ve görünüm için tek doğru kaynak: frontend/reference/personal-artifact.html (Earth görünümü)
 * İstemci: src/api/station.ts (stationApi.crew/astronaut/monitorDay/link, openMonitorStream)
 * Ortak bileşenler (astronot ekranıyla): src/shared/health/
 */
import type { StationInfo } from "../../api/station";
import { Placeholder } from "../../shared/Placeholder";

export function MonitorApp({ station }: { station: StationInfo }) {
  return (
    <Placeholder
      station={station}
      title={{ tr: "Dünya üssü ekranı", en: "Earth base screen" }}
      intro={{
        tr: "Dünya ekranı ayrı bir branch'te yapılacak. Salt okunurdur: gemiden downlink ile gelen, gemide gizlilik filtresinden geçmiş veriyi gösterir. Giriş: EARTH / EARTH.",
        en: "The Earth screen will be built in a separate branch. It is read-only: it shows data that arrived from the ship by downlink, filtered for privacy on the ship. Login: EARTH / EARTH.",
      }}
      endpoints={[
        "GET  /api/auth/hint · POST /api/auth/login (EARTH)",
        "GET  /api/monitor/crew",
        "GET  /api/monitor/astronauts/{id} · /api/monitor/astronauts/{id}/days/{day}",
        "GET  /api/link/status",
        "GET  /api/stream/monitor?access_token=… (SSE)",
        "GET  /api/catalog",
      ]}
    />
  );
}
