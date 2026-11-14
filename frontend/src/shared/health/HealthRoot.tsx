/**
 * Ortak sağlık görünümünün kökü: tema değişkenleri, yazı tipleri ve prototipin "tek dar kolon" düzeni.
 * Bütün ortak bileşenler (ve onları kullanan ekranın kendi kartları) bunun İÇİNDE olmalıdır; stil `.ahc`
 * kapsamına bağlıdır.
 *
 *   <HealthRoot>
 *     <StatusCard … /> <TodoCard … /> …
 *   </HealthRoot>
 *
 * Tema: `auto` (varsayılan) işletim sisteminin açık/koyu tercihini izler; `light` / `dark` zorlar.
 */
import type { ReactNode } from "react";

import "./fonts";
import "./health.css";

export type HealthTheme = "auto" | "light" | "dark";

export interface HealthRootProps {
  theme?: HealthTheme;
  /** Kök öğeye eklenecek sınıf (ekranın kendi stili için). */
  className?: string;
  children: ReactNode;
}

export function HealthRoot({ theme = "auto", className, children }: HealthRootProps) {
  return (
    <div className={className ? `ahc ${className}` : "ahc"} data-theme={theme === "auto" ? undefined : theme}>
      <main>{children}</main>
    </div>
  );
}
