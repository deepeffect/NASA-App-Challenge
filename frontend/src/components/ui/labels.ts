/** Arayüz metinleri ve eşlemeler (tek yerde; i18n gerekirse buradan başlanır). */
import type { EventSource, HealthSystem, Severity, StatusColor } from "../../api/client";

export const SYSTEM_LABELS: Record<HealthSystem, string> = {
  cardiovascular: "Cardiovascular",
  musculoskeletal: "Musculoskeletal",
  immune: "Immune",
  behavioral: "Behavioral health",
  sleep: "Sleep",
  radiation: "Radiation",
};

export const STATUS_LABELS: Record<StatusColor, string> = {
  green: "Normal",
  yellow: "Attention",
  red: "Critical",
  unknown: "No data",
};

export const SEVERITY_LABELS: Record<Severity, string> = {
  critical: "Critical",
  warning: "Warning",
  info: "Info",
};

/** source → "Rule / Model detection / Forecast" */
export const SOURCE_LABELS: Record<EventSource, string> = {
  rule: "Rule",
  anomaly: "Model detection",
  changepoint: "Model detection",
  forecast: "Forecast",
};

/** score → güven etiketi (<0.5 low · 0.5–0.75 medium · >0.75 high) */
export function confidenceLabel(score: number): "low" | "medium" | "high" {
  if (score < 0.5) return "low";
  if (score <= 0.75) return "medium";
  return "high";
}

export const TOOL_LABELS: Record<string, string> = {
  get_metric: "Metric data",
  get_health_summary: "Health summary",
  get_alerts: "Alerts",
  get_radiation_dose: "Radiation dose",
  get_checkins: "Check-ins",
  search_docs: "Document search",
};

export const SEVERITY_COLORS: Record<Severity, string> = {
  critical: "#f87171", // red-400
  warning: "#fb923c", // orange-400
  info: "#7dd3fc", // sky-300
};
