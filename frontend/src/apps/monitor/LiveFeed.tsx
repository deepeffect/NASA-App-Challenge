/**
 * Canlı akış (sağ panel): gemiden gelen olaylar, yeniden eskiye; her olayda gemi zamanı, Dünya'ya ulaşma
 * zamanı ve aradaki süre. Geçmiş /api/monitor/events'ten gelir (sayfa yenilenince kaybolmaz); yeni olay SSE
 * ile tetiklenir ve kısa süre vurgulanır. Bağlantı kopma / geri gelme anları ekran işareti olarak araya girer.
 */
import { Link } from "react-router";

import { type MonitorEvent, useCatalog, useFeedEvents } from "./api";
import { FEED_LIMIT } from "./config";
import { detailPath } from "./Detail";
import { EventIcon } from "./icons";
import { flashClass, type LinkMarker, useLive } from "./live";
import { fmtSeconds, fmtTime, shareKey, type TFn, useT } from "./texts";
import { SectionHead } from "./ui";

type Item = { kind: "event"; at: number; ev: MonitorEvent } | { kind: "marker"; at: number; m: LinkMarker };

function eventTitle(ev: MonitorEvent, t: TFn, solTitle: (code: string) => string): string {
  switch (ev.type) {
    case "checkin.completed":
      return t("ev_checkin_completed");
    case "checkin.shared":
      return t("ev_checkin_shared", { level: t(shareKey(ev.share)) });
    case "action.done":
      if (ev.masked || !ev.code) return t("ev_action_masked");
      return t(ev.done === false ? "ev_action_undone" : "ev_action_done", { title: solTitle(ev.code) });
    default:
      return t("ev_day_snapshot");
  }
}

export function LiveFeed() {
  const { t, locale } = useT();
  const feed = useFeedEvents(FEED_LIMIT);
  const catalog = useCatalog();
  const { markers, flashSeq } = useLive();
  const solTitle = (code: string) => catalog.data?.solutions.find((s) => s.code === code)?.title ?? code;

  const events = feed.data?.events ?? [];
  const oldest = events.length ? new Date(events[events.length - 1].earth_received_time).getTime() : 0;
  const items: Item[] = [
    ...events.map((ev) => ({ kind: "event" as const, at: new Date(ev.earth_received_time).getTime(), ev })),
    // Sadece listedeki olayların zaman aralığına düşen (veya daha yeni) bağlantı işaretleri
    ...markers.filter((m) => events.length < FEED_LIMIT || new Date(m.at).getTime() >= oldest).map((m) => ({ kind: "marker" as const, at: new Date(m.at).getTime(), m })),
  ].sort((a, b) => b.at - a.at);

  return (
    <section className="card feed" aria-labelledby="feed-h">
      <SectionHead id="feed-h" title={t("feedTitle")} intro={t("feedIntro")} />
      {feed.isPending ? (
        <p className="state-msg">{t("loading")}</p>
      ) : feed.isError && !feed.data ? (
        <p className="state-msg" role="alert">
          {t("loadError")}
        </p>
      ) : items.length === 0 ? (
        <p className="state-msg">{t("feedEmpty")}</p>
      ) : (
        <ol role="log" aria-live="polite" aria-relevant="additions" aria-labelledby="feed-h">
          {items.map((it) =>
            it.kind === "marker" ? (
              <li key={`m${it.m.id}`} className={`fitem marker ${it.m.up ? "up" : "down"}`} data-marker={it.m.up ? "up" : "down"}>
                <span className="ic">
                  <EventIcon type={it.m.up ? "link.up" : "link.down"} />
                </span>
                <div>
                  <p className="t">{t(it.m.up ? "ev_link_up" : "ev_link_down")}</p>
                  <p className="who">{t("evLinkNote", { time: fmtTime(it.m.at, locale, true) })}</p>
                </div>
              </li>
            ) : (
              <FeedEvent key={it.ev.seq} ev={it.ev} title={eventTitle(it.ev, t, solTitle)} flash={flashSeq(it.ev.seq) ? it.ev.seq : null} />
            ),
          )}
        </ol>
      )}
      {feed.data && feed.data.total > 0 && <p className="foot num">{t("feedCount", { n: events.length, total: feed.data.total })}</p>}
    </section>
  );
}

function FeedEvent({ ev, title, flash }: { ev: MonitorEvent; title: string; flash: number | null }) {
  const { t, locale } = useT();
  const transit = (new Date(ev.earth_received_time).getTime() - new Date(ev.ship_time).getTime()) / 1000;
  return (
    <li className={`fitem${flashClass(flash)}`} data-seq={ev.seq} data-type={ev.type} data-astronaut={ev.astronaut_id ?? ""}>
      <span className="ic">
        <EventIcon type={ev.type} />
      </span>
      <div>
        <p className="t">{title}</p>
        <p className="who">
          {ev.astronaut_id ? (
            <Link to={detailPath(ev.astronaut_id)} aria-label={t("openDetailOf", { id: ev.astronaut_id })}>
              {ev.astronaut_id}
            </Link>
          ) : null}
          {ev.day != null && <span>{t("evDay", { day: ev.day, mission: ev.mission_day ?? "–" })}</span>}
        </p>
      </div>
      <p className="times num">
        <span>
          {t("evShip")} <b>{fmtTime(ev.ship_time, locale, true)}</b>
        </span>
        <span>
          {t("evEarth")} <b>{fmtTime(ev.earth_received_time, locale, true)}</b>
        </span>
        <span>{t("evTransit", { s: fmtSeconds(Math.max(0, transit), locale) })}</span>
      </p>
    </li>
  );
}
