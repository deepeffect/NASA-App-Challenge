/** Durum ve ciddiyet rozetleri. Kural: durum ASLA sadece renkle anlatılmaz → ikon + metin. */
import type { ReactNode } from "react";

import type { Severity, StatusColor } from "../../api/client";
import { AlertTriangleIcon, CheckCircleIcon, HelpCircleIcon, InfoIcon, OctagonAlertIcon } from "./icons";
import { SEVERITY_LABELS, STATUS_LABELS } from "./labels";

const STATUS_STYLE: Record<StatusColor, { cls: string; Icon: typeof CheckCircleIcon }> = {
  green: { cls: "border-emerald-600/70 bg-emerald-950/60 text-emerald-300", Icon: CheckCircleIcon },
  yellow: { cls: "border-amber-500/70 bg-amber-950/60 text-amber-300", Icon: AlertTriangleIcon },
  red: { cls: "border-red-500/80 bg-red-950/70 text-red-300", Icon: OctagonAlertIcon },
  unknown: { cls: "border-slate-600 bg-slate-800 text-slate-300", Icon: HelpCircleIcon },
};

const SEVERITY_STYLE: Record<Severity, { cls: string; Icon: typeof CheckCircleIcon }> = {
  critical: { cls: "border-red-500/80 bg-red-950/70 text-red-300", Icon: OctagonAlertIcon },
  warning: { cls: "border-orange-500/70 bg-orange-950/60 text-orange-300", Icon: AlertTriangleIcon },
  info: { cls: "border-sky-600/70 bg-sky-950/60 text-sky-300", Icon: InfoIcon },
};

const SIZES = {
  sm: "gap-1 px-2 py-0.5 text-sm [&_svg]:h-4 [&_svg]:w-4",
  md: "gap-1.5 px-2.5 py-1 text-base [&_svg]:h-5 [&_svg]:w-5",
  lg: "gap-2 px-3.5 py-1.5 text-xl font-semibold [&_svg]:h-6 [&_svg]:w-6",
};

export function StatusBadge({ status, size = "md" }: { status: StatusColor; size?: keyof typeof SIZES }) {
  const { cls, Icon } = STATUS_STYLE[status];
  return (
    <span className={`inline-flex items-center rounded-full border font-medium ${cls} ${SIZES[size]}`}>
      <Icon />
      <span>{STATUS_LABELS[status]}</span>
    </span>
  );
}

export function SeverityBadge({ severity, size = "sm" }: { severity: Severity; size?: keyof typeof SIZES }) {
  const { cls, Icon } = SEVERITY_STYLE[severity];
  return (
    <span className={`inline-flex items-center rounded-full border font-medium ${cls} ${SIZES[size]}`}>
      <Icon />
      <span>{SEVERITY_LABELS[severity]}</span>
    </span>
  );
}

export function Tag({ children, tone = "slate" }: { children: ReactNode; tone?: "slate" | "violet" | "sky" }) {
  const tones = {
    slate: "border-slate-600 bg-slate-800 text-slate-200",
    violet: "border-violet-500/60 bg-violet-950/60 text-violet-200",
    sky: "border-sky-600/60 bg-sky-950/60 text-sky-200",
  };
  return <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-sm ${tones[tone]}`}>{children}</span>;
}
