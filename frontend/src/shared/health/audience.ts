import type { Audience, DayView } from "./types";

const warned = new Set<string>();

/**
 * Geliştirme uyarısı: `audience` ile verinin izleyicisi (`DayView.viewer`) aynı olmalı. Gizlilik filtresi
 * gemide uygulanır (CLAUDE.md, kural 8); Dünya görünümüne astronot verisi verilmesi bir programlama hatasıdır.
 */
export function checkAudience(component: string, audience: Audience, view: DayView | null | undefined): void {
  if (!import.meta.env.DEV || !view || view.viewer === audience) return;
  const key = `${component}:${audience}:${view.viewer}`;
  if (warned.has(key)) return;
  warned.add(key);
  console.error(`[shared/health] ${component}: audience="${audience}" ama veri viewer="${view.viewer}" için üretilmiş.`);
}
