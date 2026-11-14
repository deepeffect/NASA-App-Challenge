/** Dünya ekranının ikonları (satır içi SVG, currentColor). Hepsi süs: anlam her zaman yanındaki metinde. */
import type { ReactNode } from "react";

const S = ({ children, className }: { children: ReactNode; className?: string }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" className={className}>
    {children}
  </svg>
);

/**
 * Ürün logosu: görev yaması (dikişli kenar), eğik yörünge halkası, küçük gezegen ve onu kesen nabız çizgisi.
 * Özgün çizimdir; herhangi bir kurumun amblemini taklit etmez.
 */
export function Logo({ title }: { title?: string }) {
  return (
    <svg viewBox="0 0 64 64" role={title ? "img" : undefined} aria-hidden={title ? undefined : true} aria-label={title}>
      <defs>
        <clipPath id="mon-logo-field">
          <circle cx="32" cy="32" r="26.5" />
        </clipPath>
      </defs>
      {/* yama: kalın kenar + dikiş */}
      <circle cx="32" cy="32" r="30" fill="var(--logo-rim, #23303d)" />
      <circle cx="32" cy="32" r="28.2" fill="none" stroke="var(--logo-stitch, #9fb3c8)" strokeWidth="0.9" strokeDasharray="1.6 1.6" />
      <circle cx="32" cy="32" r="26.5" fill="var(--logo-field, #0f1a26)" />
      <g clipPath="url(#mon-logo-field)">
        {/* ufuk: alt kısımda gezegen yüzeyi */}
        <ellipse cx="32" cy="66" rx="40" ry="17" fill="var(--logo-ground, #6b3a28)" />
        <ellipse cx="32" cy="66" rx="40" ry="17" fill="none" stroke="var(--logo-ground-rim, #d96a3a)" strokeWidth="1.2" />
        {/* yörünge halkası (arka yarı) */}
        <path d="M10.5 37.5 A22 8 -16 0 1 53.5 26.5" fill="none" stroke="var(--logo-orbit, #86b6ef)" strokeWidth="1.6" opacity="0.55" />
        {/* küçük gezegen / ay */}
        <circle cx="32" cy="27" r="6.2" fill="var(--logo-moon, #c9d6e3)" />
        <circle cx="30" cy="25.5" r="1.3" fill="var(--logo-moon-shade, #9fb0c2)" />
        <circle cx="34.4" cy="29" r="0.9" fill="var(--logo-moon-shade, #9fb0c2)" />
        {/* yörünge halkası (ön yarı) */}
        <path d="M53.5 26.5 A22 8 -16 0 1 10.5 37.5" fill="none" stroke="var(--logo-orbit, #86b6ef)" strokeWidth="2" />
        <circle cx="49.6" cy="35.2" r="2" fill="var(--logo-orbit, #86b6ef)" />
        {/* nabız çizgisi */}
        <path
          d="M6 43 H20 L23.5 37 L27 49 L31.5 33 L35 46 L37.5 43 H58"
          fill="none"
          stroke="var(--logo-pulse, #f3f6f9)"
          strokeWidth="2.3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>
    </svg>
  );
}

// ---------------------------------------------------------------- alanlar
export const DomainIcon = ({ domain }: { domain: string }) => {
  switch (domain) {
    case "exposure": // radyasyon / kabin havası: yonca
      return (
        <S>
          <circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" />
          <path d="M12 9.2 9.6 4.9A8 8 0 0 1 14.4 4.9Z" fill="currentColor" stroke="none" />
          <path d="M14.4 13.4 19.3 13.4A8 8 0 0 1 16.9 17.6Z" fill="currentColor" stroke="none" />
          <path d="M9.6 13.4 7.1 17.6A8 8 0 0 1 4.7 13.4Z" fill="currentColor" stroke="none" />
          <circle cx="12" cy="12" r="9.2" />
        </S>
      );
    case "immune": // kalkan
      return (
        <S>
          <path d="M12 3 5 6v5.5c0 4.3 3 7.7 7 9.5 4-1.8 7-5.2 7-9.5V6Z" />
          <path d="m9 12 2.2 2.2L15.5 10" />
        </S>
      );
    case "bone_muscle": // kemik
      return (
        <S>
          <path d="M7.4 9.6 14.4 16.6M9.6 7.4l7 7" />
          <path d="M9.6 7.4a2.3 2.3 0 1 0-3.2 1.1 2.3 2.3 0 1 0 1 1.1M14.4 16.6a2.3 2.3 0 1 0 3.2-1.1 2.3 2.3 0 1 0-1-1.1" />
        </S>
      );
    case "cardiovascular": // kalp
      return (
        <S>
          <path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10Z" />
          <path d="M7.5 12h2.5l1.2-2 1.6 4 1.2-2h2.5" strokeWidth={1.5} />
        </S>
      );
    case "behavioral": // ay (uyku, ruh hali, stres)
      return (
        <S>
          <path d="M19.5 14.5A8 8 0 1 1 9.5 4.5a6.5 6.5 0 0 0 10 10Z" />
        </S>
      );
    default:
      return (
        <S>
          <circle cx="12" cy="12" r="8" />
        </S>
      );
  }
};

// ---------------------------------------------------------------- olaylar ve araçlar
export const EventIcon = ({ type }: { type: string }) => {
  switch (type) {
    case "checkin.completed":
      return (
        <S>
          <rect x="4" y="5" width="16" height="15" rx="2" />
          <path d="M8 3v4M16 3v4M8.5 13l2.5 2.5 4.5-4.5" />
        </S>
      );
    case "checkin.shared":
      return (
        <S>
          <path d="M12 15V4M8 8l4-4 4 4" />
          <path d="M5 13v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5" />
        </S>
      );
    case "action.done":
      return (
        <S>
          <rect x="4" y="4" width="16" height="16" rx="3" />
          <path d="m8.5 12 2.5 2.5 4.5-5" />
        </S>
      );
    case "link.up":
      return (
        <S>
          <path d="M5 12.5a10 10 0 0 1 14 0M8 15.5a5.5 5.5 0 0 1 8 0" />
          <circle cx="12" cy="19" r="1.2" fill="currentColor" />
        </S>
      );
    case "link.down":
      return (
        <S>
          <path d="M5 12.5a10 10 0 0 1 6-2.8M8 15.5a5.5 5.5 0 0 1 3-1.4" />
          <circle cx="12" cy="19" r="1.2" fill="currentColor" />
          <path d="m15 9 5 5M20 9l-5 5" />
        </S>
      );
    default: // day.snapshot
      return (
        <S>
          <path d="M20 11a8 8 0 0 0-14.3-4.9L4 8M4 4v4h4M4 13a8 8 0 0 0 14.3 4.9L20 16M20 20v-4h-4" />
        </S>
      );
  }
};

export const AlertIcon = () => (
  <S>
    <path d="M12 3.5 2.5 20h19Z" />
    <path d="M12 10v4.5M12 17.2v.1" strokeWidth={2.2} />
  </S>
);
export const LockIcon = ({ className }: { className?: string }) => (
  <S className={className}>
    <rect x="5" y="11" width="14" height="9" rx="2" />
    <path d="M8.5 11V8a3.5 3.5 0 0 1 7 0v3" />
  </S>
);
export const SunIcon = () => (
  <S>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2.5v2M12 19.5v2M4.6 4.6 6 6M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4" />
  </S>
);
export const MoonIcon = () => (
  <S>
    <path d="M19.5 14.5A8 8 0 1 1 9.5 4.5a6.5 6.5 0 0 0 10 10Z" />
  </S>
);
export const LogoutIcon = () => (
  <S>
    <path d="M9 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h3M15 16l4-4-4-4M19 12H9" />
  </S>
);
export const ChevronIcon = ({ className }: { className?: string }) => (
  <S className={className}>
    <path d="m9 6 6 6-6 6" />
  </S>
);