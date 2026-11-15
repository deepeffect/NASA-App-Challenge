/** Küçük ortak parçalar: durum etiketi (glif + metin), bölüm başlığı, tema. */
import { type ReactNode, useCallback, useEffect, useState } from "react";

/** Durum: renk + şekil + metin (0 halka, 1 üçgen, 2 karo). Metin backend'den gelir. */
export function StatusLabel({ status, label, className = "" }: { status: number; label: string; className?: string }) {
  return (
    <span className={`st s${status} ${className}`}>
      <span className={`glyph g${status}`} aria-hidden="true" />
      {label}
    </span>
  );
}

export function SectionHead({ id, title, intro, right }: { id: string; title: string; intro?: string; right?: ReactNode }) {
  return (
    <div className="sec-head">
      <div>
        <h2 id={id}>{title}</h2>
        {intro && <p>{intro}</p>}
      </div>
      {right}
    </div>
  );
}

// ---------------------------------------------------------------- tema (kiosk: varsayılan koyu)
export type Theme = "dark" | "light";
const THEME_KEY = "ahm-monitor-theme";

function initialTheme(): Theme {
  try {
    return localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>(initialTheme);
  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    try {
      localStorage.setItem(THEME_KEY, t);
    } catch {
      /* depolama kapalı olabilir */
    }
  }, []);
  // Sayfa kenarlarında (kaydırma taşması) da aynı zemin görünsün
  useEffect(() => {
    const prev = document.body.style.background;
    document.body.style.background = theme === "dark" ? "#0d1115" : "#f1f4f7";
    return () => {
      document.body.style.background = prev;
    };
  }, [theme]);
  return [theme, setTheme];
}
