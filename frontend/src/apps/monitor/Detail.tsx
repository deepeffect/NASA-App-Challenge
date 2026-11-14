/**
 * Astronot detayı: /monitor/astronaut/:id (seçili gün bugün değilse ?day=N).
 *
 * Prototipin Earth görünümü (frontend/reference/personal-artifact.html): Dünya çubuğu (astronot seçimi,
 * önceki/sonraki) + ortak sağlık bileşenleri `audience="earth"` ile: durum kartı ve 30 günlük şerit, astronota
 * gösterilen öneriler, paylaşım seviyesine göre check-in paneli, "bu günün ayrıntıları" (kimlik satırı,
 * kümülatif + tek gün skor grafiği, ölçümler tablosu). Hepsi Dünya'nın kendi verisinden (earth.db).
 *
 * Ortak bileşenler HealthRoot (.ahc) içindedir ve /me'dekiyle birebir aynı görünür: monitor.css'in hiçbir kuralı
 * .ahc ağacına uygulanmaz (bkz. monitor.css başı; smoke testi hesaplanmış stilleri karşılaştırır). Dünya
 * çubuğu ve check-in paneli ekranın kendi kartlarıdır, prototipin sınıflarıyla (health.css) çizilir.
 *
 * Önceki/sonraki: astronot mürettebattaysa mürettebat içinde, değilse 200 astronot içinde kimlik sırasıyla
 * (ikisi de döngüsel). Seçili gün astronot değişince korunur.
 */
import { type MouseEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import type { components } from "../../api/types";
import { Glyph, HealthRoot, ReadingsTable, ScoreChart, StatusCard, TodoCard, WhoRow } from "../../shared/health";
import { isNotFound, useCatalog, useCrew, useMonitorDay, useOverview } from "./api";
import { DEMO_CREW } from "./config";
import { useT } from "./texts";
import type { Theme } from "./ui";

type EarthCheckinView = components["schemas"]["EarthCheckinView"];

/** Detay adresi. Gün verilmezse astronotun bugünü açılır. */
export const detailPath = (id: string, day?: number | null): string =>
  `/monitor/astronaut/${encodeURIComponent(id)}${day ? `?day=${day}` : ""}`;

/**
 * Kartın / satırın boş bir yerine tıklanınca detaya git. Klavye ve ekran okuyucu için ayrıca kimlik bir
 * bağlantıdır; içteki bağlantı, düğme ve form öğelerinin tıklaması burada yakalanmaz.
 */
export function useOpenDetail(id: string): (e: MouseEvent) => void {
  const navigate = useNavigate();
  return (e) => {
    if ((e.target as Element).closest("a, button, input, select, summary")) return;
    if (window.getSelection()?.toString()) return; // metin seçiliyor
    navigate(detailPath(id));
  };
}

/** Döngüsel önceki / sonraki. */
function neighbours(ring: readonly string[], id: string): [string | undefined, string | undefined] {
  const i = ring.indexOf(id);
  if (i < 0 || ring.length < 2) return [undefined, undefined];
  return [ring[(i - 1 + ring.length) % ring.length], ring[(i + 1) % ring.length]];
}

export function AstronautDetail({ theme }: { theme: Theme }) {
  const { t } = useT();
  const navigate = useNavigate();
  const id = (useParams().id ?? "").toUpperCase();
  const [params, setParams] = useSearchParams();
  const crew = useCrew();
  const catalog = useCatalog();
  const overviewQ = useOverview(id);
  // Astronot değişince önceki astronotun verisi (keepPreviousData) bu astronotunmuş gibi gösterilmesin
  const overview = overviewQ.data?.astronaut.id === id ? overviewQ.data : undefined;

  const asked = Number(params.get("day"));
  const day = overview ? (Number.isInteger(asked) && asked >= 1 && asked <= overview.n_days ? asked : overview.today) : undefined;
  const dayQ = useMonitorDay(id, day);
  const md = dayQ.data && dayQ.data.view.astronaut_id === id && dayQ.data.view.day === day ? dayQ.data : undefined;

  const members = crew.data?.astronauts;
  const allIds = useMemo(() => (members ?? []).map((m) => m.astronaut.id).sort(), [members]);
  const labelOf = useMemo(() => new Map((members ?? []).map((m) => [m.astronaut.id, `${m.astronaut.id} · ${m.status_label}`])), [members]);
  const [prev, next] = neighbours(DEMO_CREW.includes(id) ? DEMO_CREW : allIds, id);

  // Başka bir astronota geçince sayfanın başına
  // Gövde süslü parantezde: yeni tarayıcılarda scrollTo bir Promise döndürür, React onu temizlik fonksiyonu sanar
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [id]);

  const keepDay = params.get("day") ? day : undefined;
  const go = (target: string) => navigate(detailPath(target, keepDay));
  const setDay = (d: number) => setParams(d === overview?.today ? {} : { day: String(d) }, { replace: true });

  const [moreOpen, setMoreOpen] = useState(true);

  return (
    <HealthRoot theme={theme}>
      <section className="card earthbar" aria-labelledby="detail-h" data-astronaut={id}>
        <div className="ci-head">
          <h1 id="detail-h" className="num">
            {id}
          </h1>
          <Link className="linkbtn" to="/monitor">
            ‹ {t("backToOverview")}
          </Link>
        </div>
        <p>
          <b>{t("detailViewTitle")}</b> {t("detailViewText")}
        </p>
        <div className="pick2">
          <select aria-label={t("pickAstronaut")} value={id} onChange={(e) => go(e.target.value)}>
            {!allIds.includes(id) && !DEMO_CREW.includes(id) && <option value={id}>{id}</option>}
            <optgroup label={t("groupCrew")}>
              {DEMO_CREW.map((x) => (
                <option key={x} value={x}>
                  {labelOf.get(x) ?? x}
                </option>
              ))}
            </optgroup>
            <optgroup label={t("groupAll")}>
              {allIds
                .filter((x) => !DEMO_CREW.includes(x))
                .map((x) => (
                  <option key={x} value={x}>
                    {labelOf.get(x) ?? x}
                  </option>
                ))}
            </optgroup>
          </select>
          <button type="button" data-nav="prev" disabled={!prev} onClick={() => prev && go(prev)} aria-label={prev ? t("prevAstronaut", { id: prev }) : undefined}>
            ‹ {prev}
          </button>
          <button type="button" data-nav="next" disabled={!next} onClick={() => next && go(next)} aria-label={next ? t("nextAstronaut", { id: next }) : undefined}>
            {next} ›
          </button>
        </div>
      </section>

      {!overview ? (
        <section className="card">
          <p className={overviewQ.isError ? "calm" : "muted"} role={overviewQ.isError ? "alert" : undefined}>
            {isNotFound(overviewQ.error) ? t("unknownAstronaut", { id }) : overviewQ.isError ? t("loadError") : t("loading")}
          </p>
        </section>
      ) : (
        <>
          <StatusCard audience="earth" strip={overview.strip} selectedDay={day ?? overview.today} onSelectDay={setDay} view={md?.view} statusLabels={catalog.data?.statuses} />
          {md ? (
            <>
              <TodoCard audience="earth" view={md.view} />
              <CheckinPanel checkin={md.checkin} />
            </>
          ) : (
            <section className="card">
              <p className="muted">{dayQ.isError ? t("loadError") : t("loading")}</p>
            </section>
          )}
          <details className="card more" open={moreOpen} onToggle={(e) => setMoreOpen((e.target as HTMLDetailsElement).open)}>
            <summary>{t("dayDetails")}</summary>
            <div className="stack">
              <WhoRow audience="earth" astronaut={overview.astronaut} />
              <ScoreChart audience="earth" points={overview.strip} selectedDay={day ?? overview.today} onSelectDay={setDay} />
              {md && catalog.data ? <ReadingsTable audience="earth" view={md.view} domains={catalog.data.domains} /> : <p className="muted">{t("loading")}</p>}
            </div>
          </details>
        </>
      )}
    </HealthRoot>
  );
}

/**
 * Check-in paneli (prototipteki #ciearth): metin backend'den, paylaşım seviyesine göre.
 *   yok / private → tek satır ("Tamamlanmış check-in yok" / "gizli tuttu")
 *   scores        → konu + "İşaretlendi / İşaret yok" (astronotun sözleri gelmez)
 *   full          → konu + astronotun yazdığı
 */
function CheckinPanel({ checkin }: { checkin: EarthCheckinView }) {
  const { t } = useT();
  const share = checkin.share ?? null;
  const shared = share === "scores" || share === "full";
  return (
    <section className="card" aria-labelledby="ci-h" data-share={share ?? "none"}>
      <div className="ci-head">
        <h2 id="ci-h">{t("checkinTitle")}</h2>
      </div>
      <div style={{ marginTop: 8 }}>
        <p className={shared ? "muted" : "calm"}>{checkin.text}</p>
        {shared && checkin.notes.length > 0 && (
          <div className="cinotes">
            {checkin.notes.map((n, i) => (
              <div key={`${n.topic}-${i}`} data-flag={n.flag ? "true" : undefined}>
                <span className="t">{n.topic}</span>
                <span>{share === "full" ? (n.text ?? "") : n.flag_text}</span>
                {n.flag && <Glyph level={1} />}
                {n.flag && share === "full" && <span className="vh">{t("flagged")}</span>}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
