/**
 * Bağlantı çubuğu (en üstte): "Gemi bağlantısı: bağlı · son temas 3 sn önce · kuyrukta 0 olay" + simüle ışık
 * gecikmesi. Bağlantı koparsa belirgin uyarı; ekran son veriyle çalışmaya devam eder.
 * Kaynak: /api/link/status (+ SSE `link` olayları), hepsi Dünya backend'inden.
 */
import { AlertIcon } from "./icons";
import { useLive, useNow } from "./live";
import { fmtAgo, fmtSeconds, fmtTime, useT } from "./texts";

export function LinkBar() {
  const { t, locale } = useT();
  const { link, earthReachable, linkUpdatedAt } = useLive();
  const now = useNow();

  if (!link) {
    return (
      <div className="linkbar" role="status">
        <span className="lk">
          <span className="dot wait" aria-hidden="true" />
          <b>{t("shipLink")}:</b> {earthReachable ? t("loading") : t("serverDown")}
        </span>
      </div>
    );
  }

  const up = earthReachable && link.connected;
  const queued = (link.pending_on_ship ?? 0) + (link.behind ?? 0);
  const state = !link.configured ? t("notConfigured") : up ? t("connected") : t("disconnected");
  const lastKnown = fmtTime(link.last_contact ?? link.snapshot_at, locale);

  return (
    <>
      <div className="linkbar" role="status" aria-live="polite" data-link={up ? "up" : "down"}>
        <span className="lk">
          <span className={`dot ${up ? "up" : "down"}`} aria-hidden="true" />
          <span>
            <b>{t("shipLink")}:</b> {state}
          </span>
        </span>
        <span className="sep" aria-hidden="true">
          ·
        </span>
        <span className="num">{link.last_contact ? t("lastContact", { ago: fmtAgo(link.last_contact, now, t) }) : t("neverContact")}</span>
        <span className="sep" aria-hidden="true">
          ·
        </span>
        <span className="num">{t("queued", { n: queued })}</span>
        <span className="delay num" title={t("lightDelayHint")}>
          {link.simulated_light_delay_minutes != null && <span>{t("lightDelay", { min: fmtSeconds(link.simulated_light_delay_minutes, locale) })}</span>}
          {link.delay_seconds != null && (
            <>
              <span className="sep" aria-hidden="true">
                ·
              </span>
              <span>{t("demoDelay", { s: fmtSeconds(link.delay_seconds, locale) })}</span>
            </>
          )}
        </span>
      </div>
      {!earthReachable ? (
        <div className="linkdown" role="alert">
          <AlertIcon />
          <div>
            <b>{t("earthDownTitle", { time: fmtTime(new Date(linkUpdatedAt).toISOString(), locale) })}</b>
            <p>{t("earthDownText")}</p>
          </div>
        </div>
      ) : (
        link.configured &&
        !link.connected && (
          <div className="linkdown" role="alert">
            <AlertIcon />
            <div>
              <b>{link.epoch ? t("linkDownTitle", { time: lastKnown }) : t("syncing")}</b>
              <p>{t("linkDownText")}</p>
            </div>
          </div>
        )
      )}
    </>
  );
}
