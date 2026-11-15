/**
 * Ortak sağlık bileşenlerinin SABİT arayüz metinleri (TR/EN).
 *
 * Veriye bağlı her metin backend'den hazır gelir ve aynen gösterilir (`DayView`, `StripDay`): durum etiketi,
 * alt başlık, gün etiketi, to-do başlığı ve gerekçesi, "Paylaşılmadı", aralık ve bayrak metinleri, dipnotlar.
 * Burada sadece backend'in göndermediği sabit etiketler vardır (tablo başlıkları, düğme adları, grafik yazıları).
 *
 * İngilizce metinler prototiple (frontend/reference/personal-artifact.html) birebir aynıdır; Türkçe terimler
 * backend'in kullandıklarıyla aynıdır (app/personal/view.py, config/catalog.yaml).
 */
import { type Lang, useLang } from "../i18n";
import type { Audience } from "./types";

export interface HealthTexts {
  /** Ondalık ayırıcı: sayılar backend'le aynı biçimde gösterilir (TR'de virgül). */
  decimal: "." | ",";
  /** Durum etiketleri, indeks = seviye (katalogdaki `statuses` ile aynı; katalog yüklenmediyse kullanılır). */
  statuses: readonly [string, string, string];

  // ---- durum kartı
  healthScore: string;
  stripLabel: (n: number) => string;
  stripTip: (day: number, score: string, status: string) => string;
  prevDay: string;
  nextDay: string;
  barHeight: string;

  // ---- to-do
  steps: string;
  hide: string;
  contactGroundIf: string;
  didIt: string;
  /** "Yaptım" düğmesi olmayan yerde (geçmiş gün, Dünya görünümü) işaretli öğenin yazısı. */
  doneMark: Record<Audience, string>;

  // ---- ölçümler
  readings: string;
  thReading: string;
  thValue: string;
  thHealthy: string;
  thFlag: string;
  areaScores: string;
  mainConcern: string;
  /** Dünya görünümünde gizli değerin maskesi (backend'in `value_text`'i ile aynı sözcük). */
  notShared: string;

  // ---- skor grafiği
  chartTitle: (n: number) => string;
  chartAria: (n: number) => string;
  /** Sadece kümülatif çizgi çizildiğinde (günlük skor verilmediyse) grafiğin adı. */
  chartAriaRunning: (n: number) => string;
  running: string;
  singleDay: string;
  tipRunning: string;
  tipSingle: string;
  normalFrom: (v: number) => string;
  unwellBelow: (v: number) => string;
  chartDay: (day: number) => string;
  tipDay: (day: number) => string;
  /** Veri setinde skor yoksa grafiğin yerine (backend notu gelmediyse). */
  noScores: string;

  // ---- kimlik satırı
  age: string;
  sex: string;
  bmi: string;
  mission: string;
  pattern: string;
  /** Veri setindeki cinsiyet kodunun gösterimi; bilinmeyen kod aynen yazılır. */
  sexValue: Record<string, string>;

  // ---- self-care penceresi
  allSolutions: string;
  close: string;
  when: string;
}

export const HEALTH_TEXTS: Record<Lang, HealthTexts> = {
  en: {
    decimal: ".",
    statuses: ["Normal", "Needs attention", "Unwell"],
    healthScore: "health score",
    stripLabel: (n) => `Health score for each of the ${n} days`,
    stripTip: (day, score, status) => `Day ${day} · score ${score} · ${status}`,
    prevDay: "Previous day",
    nextDay: "Next day",
    barHeight: "Bar height is the health score",
    steps: "Steps",
    hide: "Hide",
    contactGroundIf: "Contact ground if:",
    didIt: "Done",
    doneMark: { astronaut: "Marked as done", earth: "Marked as done by the astronaut" },
    readings: "Readings",
    thReading: "Reading",
    thValue: "Value",
    thHealthy: "Healthy",
    thFlag: "Flag",
    areaScores: "Area scores (0 to 100)",
    mainConcern: "Main concern",
    notShared: "Not shared",
    chartTitle: (n) => `Health score over the ${n} days`,
    noScores: "This dataset has no scores.",
    chartAria: (n) => `Running and single-day health score for each of the ${n} days`,
    chartAriaRunning: (n) => `Running health score for each of the ${n} days`,
    running: "Running score",
    singleDay: "Single day",
    tipRunning: "Running",
    tipSingle: "Single day",
    normalFrom: (v) => `normal from ${v}`,
    unwellBelow: (v) => `unwell below ${v}`,
    chartDay: (day) => `day ${day}`,
    tipDay: (day) => `Day ${day}`,
    age: "Age",
    sex: "Sex",
    bmi: "BMI",
    mission: "Mission",
    pattern: "Simulated pattern",
    sexValue: {},
    allSolutions: "All self-care solutions",
    close: "Close",
    when: "When:",
  },
  tr: {
    decimal: ",",
    statuses: ["Normal", "Dikkat", "Rahatsız"],
    healthScore: "sağlık skoru",
    stripLabel: (n) => `${n} günün her biri için sağlık skoru`,
    stripTip: (day, score, status) => `Gün ${day} · skor ${score} · ${status}`,
    prevDay: "Önceki gün",
    nextDay: "Sonraki gün",
    barHeight: "Çubuk yüksekliği sağlık skorudur",
    steps: "Adımlar",
    hide: "Gizle",
    contactGroundIf: "Yer ekibine haber verin:",
    didIt: "Yaptım",
    doneMark: { astronaut: "Yapıldı olarak işaretlendi", earth: "Astronot yapıldı olarak işaretledi" },
    readings: "Ölçümler",
    thReading: "Ölçüm",
    thValue: "Değer",
    thHealthy: "Sağlıklı aralık",
    thFlag: "İşaret",
    areaScores: "Alan skorları (0–100)",
    mainConcern: "Ana endişe",
    notShared: "Paylaşılmadı",
    chartTitle: (n) => `${n} günlük sağlık skoru`,
    noScores: "Bu veri setinde skor yok.",
    chartAria: (n) => `${n} günün her biri için kümülatif ve tek günlük sağlık skoru`,
    chartAriaRunning: (n) => `${n} günün her biri için kümülatif sağlık skoru`,
    running: "Kümülatif skor",
    singleDay: "Tek gün",
    tipRunning: "Kümülatif",
    tipSingle: "Tek gün",
    normalFrom: (v) => `${v} ve üzeri normal`,
    unwellBelow: (v) => `${v} altı rahatsız`,
    chartDay: (day) => `${day}. gün`,
    tipDay: (day) => `Gün ${day}`,
    age: "Yaş",
    sex: "Cinsiyet",
    bmi: "VKİ",
    mission: "Görev",
    pattern: "Simülasyon deseni",
    sexValue: { M: "E", F: "K" },
    allSolutions: "Tüm öz bakım çözümleri",
    close: "Kapat",
    when: "Ne zaman:",
  },
};

/** Seçili arayüz dilindeki sabit metinler. */
export function useHealthTexts(): HealthTexts {
  return HEALTH_TEXTS[useLang().lang];
}

/** JS `toFixed` ile aynı yuvarlama (prototip ve backend `to_fixed`); TR'de ondalık virgül. */
export function formatNumber(value: number, decimals: number, t: Pick<HealthTexts, "decimal">): string {
  const s = value.toFixed(decimals);
  return t.decimal === "," ? s.replace(".", ",") : s;
}

/** Backend'in `num_plain`'i gibi: sayıyı olduğu gibi yazar (24.7 → "24,7"), yuvarlamaz. */
export function formatPlain(value: number, t: Pick<HealthTexts, "decimal">): string {
  const s = String(value);
  return t.decimal === "," ? s.replace(".", ",") : s;
}
