/**
 * Mürettebat: DEMO_CREW'daki astronotlar büyük kartlar halinde. Kart: durum (ikon + metin), kümülatif skor,
 * 30 günlük skor sparkline'ı, 5 alan ikon şeridi, son etkinlik ("2 dk önce"; son 10 dakikadaysa "Aktif" rozeti),
 * terminal durumu ("çevrimiçi" / "çevrimdışı · son görülme 5 dk önce"; gemiyle bağlantı yoksa "bilinmiyor"),
 * son check-in zamanı ve paylaşım seviyesi. Gemi saatiyle gelen zamanlar geminin saatine göre (useShipNow).
 * Yeni olay gelince kart kısa süre vurgulanır (live.tsx). Karta veya kimliğe tıklanınca astronot detayı açılır.
 */
import { Link } from "react-router";

import { AreaLegend, AreaStrip } from "./AreaStrip";
import type { TerminalStatus } from "../../api/station";
import { type MonitorCrewMember, type MonitorEvent, useCatalog, useCheckinTimes, useCrew, useLastActivity, useMonitorDay, useOverview } from "./api";
import { ACTIVE_WINDOW_MS, DEMO_CREW } from "./config";
import { detailPath, useOpenDetail } from "./Detail";
import { ActivityIcon, TerminalIcon } from "./icons";
import { flashClass, useLive, useShipNow } from "./live";
import { Sparkline } from "./Sparkline";
import { fmtAgo, fmtTime, shareKey, useT } from "./texts";
import { SectionHead, StatusLabel } from "./ui";

export function CrewSection() {
  const { t } = useT();
  const crew = useCrew();
  const checkins = useCheckinTimes();
  const byId = new Map((crew.data?.astronauts ?? []).map((m) => [m.astronaut.id, m]));

  return (
    <section aria-labelledby="crew-h">
      <SectionHead id="crew-h" title={t("crewTitle")} intro={t("crewIntro")} />
      <div className="crew-grid">
        {DEMO_CREW.map((id) => {
          const m = byId.get(id);
          if (!m)
            return (
              <article key={id} className="card ccard skeleton" aria-busy={crew.isPending}>
                <span className="ccard-id">{id}</span>
                <span>{crew.isPending ? t("loading") : crew.isError ? t("loadError") : t("noData")}</span>
              </article>
            );
          return <CrewCard key={id} member={m} checkin={checkins.data?.get(id)} />;
        })}
      </div>
      <AreaLegend />
    </section>
  );
}

export function CheckinWhen({ share, today, checkin }: { share: string | null | undefined; today: number; checkin: MonitorEvent | undefined }) {
  const { t, locale } = useT();
  if (!share) return <>{t("noCheckin")}</>;
  if (!checkin || checkin.day !== today) return <>{t("timeUnknown")}</>;
  return <>{t("shipTimeShort", { time: fmtTime(checkin.ship_time, locale) })}</>;
}

function CrewCard({ member, checkin }: { member: MonitorCrewMember; checkin: MonitorEvent | undefined }) {
  const { t, locale } = useT();
  const { flashFor } = useLive();
  const a = member.astronaut;
  const open = useOpenDetail(a.id);
  const overview = useOverview(a.id);
  const day = useMonitorDay(a.id, member.today);
  const catalog = useCatalog();
  const activity = useLastActivity(a.id);
  const clock = useShipNow(5_000); // geminin saati: son etkinlik ve son görülme gemi saatiyle gelir
  const hid = `card-${a.id}`;
  const v = day.data?.view.day === member.today ? day.data.view : undefined;
  const priv = v?.readings.filter((r) => r.private) ?? [];
  // "Bugün" alanları astronotun kendi gününden (olayda ~10 ms'de yenilenir); /crew (200 kişi, ~0,7 sn) yedek
  const now = v
    ? { status: v.status, label: v.status_label, subtitle: v.subtitle, score: v.score_text, ground: v.ground, share: v.share ?? null }
    : { status: member.status, label: member.status_label, subtitle: member.subtitle, score: member.score_text, ground: member.ground, share: member.share ?? null };
  // Son etkinlik gemi saatiyle (astronotun yaptığı an); "Aktif" = son ACTIVE_WINDOW_MS içinde
  const last = activity.data ?? null;
  const active = last !== null && clock - new Date(last.ship_time).getTime() <= ACTIVE_WINDOW_MS;
  const activeMin = Math.round(ACTIVE_WINDOW_MS / 60_000);

  return (
    <article
      className={`card ccard open-detail is-s${now.status}${flashClass(flashFor(a.id))}`}
      aria-labelledby={hid}
      data-astronaut={a.id}
      data-active={active ? "true" : "false"}
      onClick={open}
    >
      <div className="ccard-top">
        <span className="ccard-idrow">
          <Link className="ccard-id" id={hid} to={detailPath(a.id)}>
            {a.id}
          </Link>
          {active && (
            <span className="active-badge" title={t("activeHint", { min: activeMin })}>
              <ActivityIcon />
              {t("active")}
            </span>
          )}
        </span>
        <span className="ccard-meta">
          {a.age !== null && a.sex !== null
            ? t("cardDay", { age: a.age, sex: a.sex, day: member.mission_day })
            : t("cardDayOnly", { day: member.mission_day })}
        </span>
      </div>
      <div className="ccard-head">
        <div>
          <div className="ccard-state">
            <StatusLabel status={now.status} label={now.label} />
          </div>
          <p className="ccard-sub">{now.subtitle}</p>
        </div>
        <div className="ccard-score">
          <b>{now.score}</b>
          <span>{t("score")}</span>
        </div>
      </div>
      {now.ground && (
        <p className="groundtag">
          <span className="glyph g2" aria-hidden="true" />
          {t("groundFlag")}
        </p>
      )}
      {overview.data ? <Sparkline strip={overview.data.strip} /> : <div style={{ height: 82 }} aria-busy="true" />}
      {v && catalog.data ? <AreaStrip view={v} catalog={catalog.data} /> : <div style={{ height: 52 }} aria-busy="true" />}
      <div className="ccard-foot">
        <div className="row" data-last-activity={last?.ship_time ?? ""}>
          <span>{t("lastActivity")}</span>
          <span className="num" title={last ? t("shipTimeShort", { time: fmtTime(last.ship_time, locale, true) }) : undefined}>
            {last ? fmtAgo(last.ship_time, clock, t) : activity.isPending ? "…" : t("noActivity")}
          </span>
        </div>
        <TerminalRow terminal={member.terminal} clock={clock} />
        <div className="row">
          <span>{t("lastCheckin")}</span>
          <span className="num">
            <CheckinWhen share={now.share} today={member.today} checkin={checkin} />
          </span>
        </div>
        <div className="row">
          <span>{t("sharing")}</span>
          <span data-share={now.share ?? "none"}>{t(shareKey(now.share))}</span>
        </div>
        {priv.length > 0 && (
          // Ruh hali / stres: Dünya sadece astronot o günün check-in'ini paylaştıysa görür
          <div className="row" data-private={priv.every((r) => r.hidden) ? "hidden" : "shared"}>
            <span>{priv.map((r) => r.label).join(" · ")}</span>
            <span className="num">{priv.every((r) => r.hidden) ? priv[0].value_text : priv.map((r) => r.value_text).join(" · ")}</span>
          </div>
        )}
      </div>
    </article>
  );
}

/**
 * "Terminal" satırı (ikon + metin). Gemiyle bağlantı yokken (veya bu istasyona ulaşılamıyorken) terminalin şu anki
 * durumu bilinmez: "bilinmiyor (bağlantı yok)" — son bilinen sadece ipucunda; asla "çevrimdışı" denmez. Bağlantı
 * durumu canlıdır (SSE): kopunca /crew'un yenilenmesi beklenmez.
 */
function TerminalRow({ terminal, clock }: { terminal: TerminalStatus; clock: number }) {
  const { t, locale } = useT();
  const { link, earthReachable } = useLive();
  const linkUp = link === undefined ? terminal.state !== "unknown" : earthReachable && link.connected;
  // /crew bağlantı yokken okunduysa "unknown" der; bağlantı geri geldiyse son bilineni göster (yenilenmesi yolda)
  const state = !linkUp ? "unknown" : terminal.state === "unknown" ? (terminal.last_known ?? "never") : terminal.state;
  const seen = terminal.last_seen ? fmtTime(terminal.last_seen, locale, true) : null;
  const text =
    state === "online"
      ? t("terminalOnline")
      : state === "offline"
        ? t("terminalOffline", { ago: fmtAgo(terminal.last_seen, clock, t) })
        : state === "never"
          ? t("terminalNever")
          : t("terminalUnknown");
  const hint =
    state === "unknown"
      ? terminal.last_known && seen
        ? t("terminalUnknownHint", { state: t(terminal.last_known === "online" ? "terminalOnline" : "terminalOfflineShort"), time: seen })
        : t("terminalUnknownNeverHint")
      : state === "never"
        ? t("terminalNeverHint")
        : seen
          ? t("terminalSeenHint", { time: seen })
          : undefined;
  return (
    <div className="row" data-terminal={state} data-last-seen={terminal.last_seen ?? ""}>
      <span>{t("terminal")}</span>
      <span className="term" title={hint}>
        <TerminalIcon state={state} />
        <span className="num">{text}</span>
      </span>
    </div>
  );
}
