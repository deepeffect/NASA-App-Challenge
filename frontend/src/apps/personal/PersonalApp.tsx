/**
 * Astronot ekranı (gemi, /me) — YER TUTUCU. Kişisel ekran ekibi kendi branch'inde yapacak.
 * Kurallar ve görünüm için tek doğru kaynak: frontend/reference/personal-artifact.html
 * İstemci: src/api/station.ts (stationApi.hint/login/me/day/checkin/turn/share/resetCheckin/actionDone, chat)
 * Ortak bileşenler (Dünya ekranıyla): src/shared/health/
 */
import type { StationInfo } from "../../api/station";
import { Placeholder } from "../../shared/Placeholder";

export function PersonalApp({ station }: { station: StationInfo }) {
  return (
    <Placeholder
      station={station}
      title={{ tr: "Astronot ekranı", en: "Astronaut screen" }}
      intro={{
        tr: "Kişisel ekran ayrı bir branch'te yapılacak. Kurallar ve görünüm için tek doğru kaynak: frontend/reference/personal-artifact.html. Astronot terminali bu adresi açar: http://<gemi>:8000/me",
        en: "The personal screen will be built in a separate branch. Single source of truth for rules and layout: frontend/reference/personal-artifact.html. The astronaut terminal opens http://<ship>:8000/me",
      }}
      endpoints={[
        "GET  /api/auth/hint · POST /api/auth/login · GET /api/auth/me",
        "GET  /api/me · GET /api/me/days/{day}",
        "GET  /api/checkin · GET /api/checkin/days/{day}",
        "POST /api/checkin/turn · /api/checkin/share · /api/checkin/reset",
        "POST /api/actions/done · POST /api/chat (SSE)",
        "GET  /api/catalog",
      ]}
    />
  );
}
