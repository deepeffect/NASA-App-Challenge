/** Arayüz metinleri ve eşlemeler (tek yerde; i18n gerekirse buradan başlanır). */
import type { EventSource, HealthSystem, Severity, StatusColor } from "../../api/client";

export const SYSTEM_LABELS: Record<HealthSystem, string> = {
  cardiovascular: "Kardiyovasküler",
  musculoskeletal: "Kas-iskelet",
  immune: "Bağışıklık",
  behavioral: "Davranışsal sağlık",
  sleep: "Uyku",
  radiation: "Radyasyon",
};

export const STATUS_LABELS: Record<StatusColor, string> = {
  green: "Normal",
  yellow: "Dikkat",
  red: "Kritik",
  unknown: "Veri yok",
};

export const SEVERITY_LABELS: Record<Severity, string> = {
  critical: "Kritik",
  warning: "Uyarı",
  info: "Bilgi",
};

/** source → "Kural / Model tespiti / Tahmin" */
export const SOURCE_LABELS: Record<EventSource, string> = {
  rule: "Kural",
  anomaly: "Model tespiti",
  changepoint: "Model tespiti",
  forecast: "Tahmin",
};

/** score → güven etiketi (<0,5 düşük · 0,5–0,75 orta · >0,75 yüksek) */
export function confidenceLabel(score: number): "düşük" | "orta" | "yüksek" {
  if (score < 0.5) return "düşük";
  if (score <= 0.75) return "orta";
  return "yüksek";
}

export const TOOL_LABELS: Record<string, string> = {
  get_metric: "Metrik verisi",
  get_health_summary: "Sağlık özeti",
  get_alerts: "Uyarılar",
  get_radiation_dose: "Radyasyon dozu",
  get_checkins: "Check-in'ler",
  search_docs: "Belge araması",
};

export const SEVERITY_COLORS: Record<Severity, string> = {
  critical: "#f87171", // red-400
  warning: "#fb923c", // orange-400
  info: "#7dd3fc", // sky-300
};
