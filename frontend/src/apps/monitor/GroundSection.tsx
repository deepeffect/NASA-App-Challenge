/**
 * Yer desteği listesi: görünür ölçümlerine göre yer desteği gereken astronotlar (MonitorCrewMember.ground;
 * Dünya'da backend sadece görünür ölçümlerden hesaplar, paylaşılmamış ruh hali / stres etkilemez).
 * En düşük skor üstte. Açılınca o günün çok dışında olan görünür ölçümleri (/days/{bugün}) gösterilir.
 */
import { useState } from "react";

import { type MonitorCrewMember, useCrew, useMonitorDay } from "./api";
import { ChevronIcon } from "./icons";
import { flashClass, useLive } from "./live";
import { useT } from "./texts";
import { SectionHead, StatusLabel } from "./ui";

export function GroundSection() {
  const { t } = useT();
  const crew = useCrew();
  const list = (crew.data?.astronauts ?? []).filter((m) => m.ground).sort((a, b) => a.score - b.score || a.astronaut.id.localeCompare(b.astronaut.id));

  return (
    <section className="card" aria-labelledby="ground-h">
      <SectionHead id="ground-h" title={`${t("groundTitle")}${crew.data ? ` (${list.length})` : ""}`} intro={t("groundIntro")} />
      {crew.isPending ? (
        <p className="state-msg">{t("loading")}</p>
      ) : list.length === 0 ? (
        <p className="calm">{crew.isError && !crew.data ? t("loadError") : t("groundNone")}</p>
      ) : (
        <div className="glist">
          {list.map((m) => (
            <GroundRow key={m.astronaut.id} member={m} />
          ))}
        </div>
      )}
    </section>
  );
}

function GroundRow({ member }: { member: MonitorCrewMember }) {
  const [open, setOpen] = useState(false);
  const { flashFor } = useLive();
  const a = member.astronaut;
  return (
    <details className={flashClass(flashFor(a.id)).trim()} data-astronaut={a.id} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>
        <b>{a.id}</b>
        <span className="ink2">{a.mission_label}</span>
        <StatusLabel status={member.status} label={member.status_label} />
        <span className="score num">{member.score_text}</span>
        <span className="sub">{member.subtitle}</span>
        <ChevronIcon className="chev" />
      </summary>
      {open && <FarOut member={member} />}
    </details>
  );
}

function FarOut({ member }: { member: MonitorCrewMember }) {
  const { t } = useT();
  const day = useMonitorDay(member.astronaut.id, member.today);
  if (!day.data) return <p className="why muted">{day.isError ? t("loadError") : t("loading")}</p>;
  const v = day.data.view;
  const far = v.readings.filter((r) => !r.hidden && r.level === 2);
  return (
    <div className="why">
      {v.ground_text && <p className="ink2">{v.ground_text}</p>}
      <p className="muted">{t("groundFarOut")}</p>
      {far.map((r) => (
        <p key={r.col} className="r">
          <span className="glyph g2" aria-hidden="true" />
          <span>
            <b>{r.label}</b> <span className="num">{r.value_text}</span> <span className="muted">{r.unit}</span>
          </span>
          <span className="muted num">{t("healthyRange", { range: r.healthy_text })}</span>
          <span className="sr">{r.flag_text}</span>
        </p>
      ))}
    </div>
  );
}
