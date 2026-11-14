/** Bağımlılıksız küçük SVG ikon seti (offline çalışma için harici ikon fontu yok). */
import type { ReactNode } from "react";

export interface IconProps {
  className?: string;
  title?: string;
}

function makeIcon(paths: ReactNode, displayName: string) {
  const Icon = ({ className = "h-5 w-5", title }: IconProps) => (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
    >
      {title && <title>{title}</title>}
      {paths}
    </svg>
  );
  Icon.displayName = displayName;
  return Icon;
}

export const CheckCircleIcon = makeIcon(
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="m8 12 3 3 5-6" />
  </>,
  "CheckCircleIcon",
);
export const AlertTriangleIcon = makeIcon(
  <>
    <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
    <path d="M12 9v4" />
    <path d="M12 17h.01" />
  </>,
  "AlertTriangleIcon",
);
export const OctagonAlertIcon = makeIcon(
  <>
    <path d="M7.9 2h8.2L22 7.9v8.2L16.1 22H7.9L2 16.1V7.9z" />
    <path d="M12 8v4" />
    <path d="M12 16h.01" />
  </>,
  "OctagonAlertIcon",
);
export const HelpCircleIcon = makeIcon(
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3" />
    <path d="M12 17h.01" />
  </>,
  "HelpCircleIcon",
);
export const InfoIcon = makeIcon(
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 16v-4" />
    <path d="M12 8h.01" />
  </>,
  "InfoIcon",
);
export const DatabaseIcon = makeIcon(
  <>
    <ellipse cx="12" cy="5" rx="8" ry="3" />
    <path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
    <path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
  </>,
  "DatabaseIcon",
);
export const SendIcon = makeIcon(
  <>
    <path d="m22 2-7 20-4-9-9-4z" />
    <path d="M22 2 11 13" />
  </>,
  "SendIcon",
);
export const StopIcon = makeIcon(<rect x="6" y="6" width="12" height="12" rx="2" />, "StopIcon");
export const ArrowLeftIcon = makeIcon(
  <>
    <path d="M19 12H5" />
    <path d="m12 19-7-7 7-7" />
  </>,
  "ArrowLeftIcon",
);
export const SatelliteIcon = makeIcon(
  <>
    <path d="M13 7 9 3 5 7l4 4" />
    <path d="m17 11 4 4-4 4-4-4" />
    <path d="m8 12 4 4 6-6-4-4z" />
    <path d="M16 8 18 6" />
    <path d="M5 19c1.5 0 3-1.5 3-3" />
  </>,
  "SatelliteIcon",
);
export const ClockIcon = makeIcon(
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </>,
  "ClockIcon",
);
