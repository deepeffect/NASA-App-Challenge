/**
 * Kimlik satırı: yaş, cinsiyet, VKİ, görev ve veri setindeki simülasyon deseni. Prototip: <div class="who">.
 * Görev ve desen adları backend'den çevrilmiş gelir (`mission_label`, `profile_label`).
 */
import { formatPlain, useHealthTexts } from "./texts";
import type { Audience, CrewInfo } from "./types";

export interface WhoRowProps {
  audience: Audience;
  astronaut: CrewInfo;
}

export function WhoRow({ audience, astronaut }: WhoRowProps) {
  const t = useHealthTexts();
  return (
    <div className="who" data-audience={audience}>
      <span>
        {t.age} <b>{astronaut.age}</b>
      </span>
      <span>
        {t.sex} <b>{t.sexValue[astronaut.sex] ?? astronaut.sex}</b>
      </span>
      <span>
        {t.bmi} <b>{formatPlain(astronaut.bmi, t)}</b>
      </span>
      <span>
        {t.mission} <b>{astronaut.mission_label}</b>
      </span>
      <span>
        {t.pattern} <b>{astronaut.profile_label}</b>
      </span>
    </div>
  );
}
