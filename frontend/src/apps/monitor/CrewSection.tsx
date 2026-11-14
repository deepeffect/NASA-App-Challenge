/**
 * Mürettebat: DEMO_CREW'daki astronotlar büyük kartlar halinde. Kart: durum (ikon + metin), kümülatif skor,
 * 30 günlük skor sparkline'ı, 5 alan ikon şeridi, son check-in zamanı ve paylaşım seviyesi.
 * Yeni olay gelince kart kısa süre vurgulanır (live.tsx). Karta veya kimliğe tıklanınca astronot detayı açılır.
 */
import { Link } from "react-router";

import { AreaLegend, AreaStrip } from "./AreaStrip";
import { type MonitorCrewMember, type MonitorEvent, useCatalog, useCheckinTimes, useCrew, useMonitorDay, useOverview } from "./api";
import { DEMO_CREW } from "./config";
import { detailPath, useOpenDetail } from "./Detail";
import { flashClass, useLive } from "./live";
import { Sparkline } from "./Sparkline";
import { fmtTime, shareKey, useT } from "./texts";
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
  const { t } = useT();
  const { flashFor } = useLive();
  const a = member.astronaut;
  const open = useOpenDetail(a.id);
  const overview = useOverview(a.id);
  const day = useMonitorDay(a.id, member.today);
  const catalog = useCatalog();
  const hid = `card-${a.id}`;
  const v = day.data?.view.day === member.today ? day.data.view : undefined;
  const priv = v?.readings.filter((r) => r.private) ?? [];
  // "Bugün" alanları astronotun kendi gününden (olayda ~10 ms'de yenilenir); /crew (200 kişi, ~0,7 sn) yedek
  const now = v
    ? { status: v.status, label: v.status_label, subtitle: v.subtitle, score: v.score_text, ground: v.ground, share: v.share ?? null }
    : { status: member.status, label: member.status_label, subtitle: member.subtitle, score: member.score_text, ground: member.ground, share: member.share ?? null };

  return (
    <article className={`card ccard open-detail is-s${now.status}${flashClass(flashFor(a.id))}`} aria-labelledby={hid} data-astronaut={a.id} onClick={open}>
      <div className="ccard-top">
        <Link className="ccard-id" id={hid} to={detailPath(a.id)} aria-label={t("openDetailOf", { id: a.id })}>
          {a.id}
        </Link>
        <span className="ccard-meta">{t("cardDay", { age: a.age, sex: a.sex, day: member.mission_day })}</span>
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
