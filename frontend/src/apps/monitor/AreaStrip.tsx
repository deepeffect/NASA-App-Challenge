/**
 * 5 alan için küçük ikon şeridi (katalogdaki alan sırası: ortam, bağışıklık, kemik-kas, kalp, davranış).
 * Her alan: ikon + kısa ad + o alandaki GÖRÜNÜR ölçümlerin en kötü seviyesi (üçgen = aralık dışında,
 * karo = çok dışında). Seviyeler backend'den gelir (ReadingView.level); burada eşik hesaplanmaz.
 * Paylaşılmamış ölçüm (ruh hali / stres) kilitle gösterilir ve seviyeye katılmaz. Ana endişe çerçeveli.
 */
import type { DayView, PersonalCatalog } from "../../api/station";
import { DomainIcon, LockIcon } from "./icons";
import { domainKey, type TFn, useT } from "./texts";

interface AreaState {
  id: string;
  label: string;
  short: string;
  level: 0 | 1 | 2;
  hidden: number;
  concern: boolean;
  flagged: string[];
}

export function areaStates(view: DayView, catalog: PersonalCatalog, t: TFn): AreaState[] {
  return catalog.domains.map((d) => {
    const rs = view.readings.filter((r) => r.domain === d.id);
    const visible = rs.filter((r) => !r.hidden && r.level !== null);
    const level = Math.max(0, ...visible.map((r) => r.level ?? 0)) as 0 | 1 | 2;
    const key = domainKey(d.id);
    return {
      id: d.id,
      label: d.label,
      short: key ? t(key) : d.label,
      level,
      hidden: rs.filter((r) => r.hidden).length,
      concern: view.main_concern === d.id,
      flagged: visible.filter((r) => (r.level ?? 0) > 0).map((r) => `${r.label} ${r.value_text}`),
    };
  });
}

function describe(a: AreaState, t: TFn): string {
  const parts = [`${a.label}: ${a.level === 2 ? t("levelFar") : a.level === 1 ? t("levelOut") : t("levelOk")}`];
  if (a.flagged.length) parts[0] += ` (${a.flagged.join(", ")})`;
  if (a.concern) parts.push(t("mainConcern"));
  if (a.hidden) parts.push(t("partlyHidden", { n: a.hidden }));
  return parts.join(" · ");
}

export function AreaStrip({ view, catalog }: { view: DayView; catalog: PersonalCatalog }) {
  const { t } = useT();
  const areas = areaStates(view, catalog, t);
  return (
    <ul className="areas" aria-label={t("areasLabel")} style={{ listStyle: "none", margin: 0, padding: 0 }}>
      {areas.map((a) => {
        const text = describe(a, t);
        return (
          <li key={a.id} className={`area l${a.level}${a.concern ? " concern" : ""}`} title={text} data-area={a.id}>
            <span className="ic">
              <DomainIcon domain={a.id} />
              {a.level > 0 && <span className={`glyph g${a.level}`} aria-hidden="true" />}
              {a.hidden > 0 && <LockIcon className="lock" />}
            </span>
            <span className="lb" aria-hidden="true">
              {a.short}
            </span>
            <span className="sr">{text}</span>
          </li>
        );
      })}
    </ul>
  );
}

export function AreaLegend() {
  const { t } = useT();
  return (
    <p className="legend">
      <span>
        <span className="glyph g1" aria-hidden="true" />
        {t("legendOut")}
      </span>
      <span>
        <span className="glyph g2" aria-hidden="true" />
        {t("legendFar")}
      </span>
      <span>
        <LockIcon />
        {t("legendHidden")}
      </span>
      <span>
        <span className="concern-key" aria-hidden="true" />
        {t("legendConcern")}
      </span>
    </p>
  );
}
