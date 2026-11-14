import { Link } from "react-router";

import type { CrewMember } from "../../api/client";
import { StatusBadge } from "../../components/ui/Badges";
import { fmtNum } from "../../components/ui/format";
import { SYSTEM_LABELS } from "../../components/ui/labels";

const RING = {
  green: "hover:border-emerald-600",
  yellow: "border-amber-600/60 hover:border-amber-400",
  red: "border-red-600/70 hover:border-red-400",
  unknown: "hover:border-slate-500",
};

export function CrewCard({ member }: { member: CrewMember }) {
  const { active_events: c } = member;
  return (
    <Link
      to={`/legacy/astronauts/${member.id}`}
      className={`block rounded-2xl border border-slate-800 bg-slate-900/80 p-5 transition-colors ${RING[member.status]}`}
      aria-label={`${member.name} detayına git`}
    >
      <div className="min-w-0">
        <p className="truncate text-2xl font-bold" title={member.name}>{member.name}</p>
        <p className="truncate text-slate-400" title={member.role ?? member.id}>{member.role ?? member.id}</p>
      </div>
      <div className="mt-3">
        <StatusBadge status={member.status} size="lg" />
      </div>

      <dl className="mt-4 grid grid-cols-3 gap-3 text-center">
        <div className="rounded-xl bg-slate-950/60 p-2">
          <dt className="text-sm text-slate-400">Skor</dt>
          <dd className="text-2xl font-semibold">{fmtNum(member.score, 0)}</dd>
        </div>
        <div className="rounded-xl bg-slate-950/60 p-2">
          <dt className="text-sm text-slate-400">Kritik</dt>
          <dd className={`text-2xl font-semibold ${c.critical ? "text-red-300" : ""}`}>{c.critical}</dd>
        </div>
        <div className="rounded-xl bg-slate-950/60 p-2">
          <dt className="text-sm text-slate-400">Uyarı</dt>
          <dd className={`text-2xl font-semibold ${c.warning ? "text-orange-300" : ""}`}>{c.warning}</dd>
        </div>
      </dl>

      <p className="mt-4 text-slate-300">
        {member.attention_systems.length
          ? `Dikkat: ${member.attention_systems.map((s) => SYSTEM_LABELS[s]).join(", ")}`
          : "Tüm sistemler normal"}
      </p>
    </Link>
  );
}
