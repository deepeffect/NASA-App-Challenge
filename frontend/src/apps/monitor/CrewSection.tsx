/**
 * Mürettebat: DEMO_CREW'daki astronotlar büyük kartlar halinde. Kart: durum (ikon + metin), kümülatif skor,
 * 30 günlük skor sparkline'ı, 5 alan ikon şeridi, son check-in zamanı ve paylaşım seviyesi.
 * Yeni olay gelince kart kısa süre vurgulanır (live.tsx).
 */
import { AreaLegend, AreaStrip } from "./AreaStrip";
import { type MonitorCrewMember, type MonitorEvent, useCatalog, useCheckinTimes, useCrew, useMonitorDay, useOverview } from "./api";
import { DEMO_CREW } from "./config";
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

export function CheckinWhen({ member, checkin }: { member: MonitorCrewMember; checkin: MonitorEvent | undefined }) {
  const { t, locale } = useT();
  if (!member.share) return <>{t("noCheckin")}</>;
  if (!checkin || checkin.day !== member.today) return <>{t("timeUnknown")}</>;
  return <>{t("shipTimeShort", { time: fmtTime(checkin.ship_time, locale) })}</>;
}

function CrewCard({ member, checkin }: { member: MonitorCrewMember; checkin: MonitorEvent | undefined }) {
  const { t } = useT();
  const { flashFor } = useLive();
  const a = member.astronaut;
  const overview = useOverview(a.id);
  const day = useMonitorDay(a.id, member.today);
  const catalog = useCatalog();
  const hid = `card-${a.id}`;
  const priv = day.data?.view.readings.filter((r) => r.private) ?? [];

  return (
    <article className={`card ccard is-s${member.status}${flashClass(flashFor(a.id))}`} aria-labelledby={hid} data-astronaut={a.id}>
      <div className="ccard-top">
        <span className="ccard-id" id={hid}>
          {a.id}
        </span>
        <span className="ccard-meta">
          {a.mission_label} · {t("ageSex", { age: a.age, sex: a.sex })}
          <br />
          {t("missionDay", { n: member.mission_day })}
        </span>
      </div>
      <div className="ccard-head">
        <div>
          <div className="ccard-state">
            <StatusLabel status={member.status} label={member.status_label} />
          </div>
          <p className="ccard-sub">{member.subtitle}</p>
        </div>
        <div className="ccard-score">
          <b>{member.score_text}</b>
          <span>{t("score")}</span>
        </div>
      </div>
      {member.ground && (
        <p className="groundtag">
          <span className="glyph g2" aria-hidden="true" />
          {t("groundFlag")}
        </p>
      )}
      {overview.data ? <Sparkline strip={overview.data.strip} /> : <div style={{ height: 82 }} aria-busy="true" />}
      {day.data && catalog.data ? <AreaStrip view={day.data.view} catalog={catalog.data} /> : <div style={{ height: 52 }} aria-busy="true" />}
      <div className="ccard-foot">
        <div className="row">
          <span>{t("lastCheckin")}</span>
          <span className="num">
            <CheckinWhen member={member} checkin={checkin} />
          </span>
        </div>
        <div className="row">
          <span>{t("sharing")}</span>
          <span data-share={member.share ?? "none"}>{t(shareKey(member.share))}</span>
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
