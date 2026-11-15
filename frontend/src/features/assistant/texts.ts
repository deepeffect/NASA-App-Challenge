/**
 * Asistan kartlarının arayüz metinleri (TR/EN) — main'in dil sistemiyle (shared/i18n) aynı desen.
 * Asistan API'sinin kendi cevapları (rapor, açıklama, sohbet) o API'nin dilinde gelir; burada sadece
 * kart başlıkları, durum ve hata metinleri vardır.
 */
import { currentLang, type Lang, useLang } from "../../shared/i18n";

const TEXTS = {
  alertsTitle: { tr: "Asistan uyarıları", en: "Assistant alerts" },
  refresh: { tr: "Yenile", en: "Refresh" },
  loadingAlerts: { tr: "Uyarılar yükleniyor…", en: "Loading alerts…" },
  noAlerts: { tr: "KIRMIZI veya SARI uyarı yok.", en: "No RED or YELLOW alerts." },
  levelRed: { tr: "Kritik (KIRMIZI)", en: "Critical (RED)" },
  levelYellow: { tr: "Dikkat (SARI)", en: "Caution (YELLOW)" },
  aiExplanation: { tr: "Yapay zekâ açıklaması", en: "AI explanation" },
  noExplanation: {
    tr: "Yapay zekâ açıklaması yok; yukarıdaki kural tabanlı mesaj geçerlidir.",
    en: "AI explanation unavailable; the rule-based message above still applies.",
  },
  reportTitle: { tr: "Günlük rapor", en: "Daily report" },
  regenerate: { tr: "Yeniden üret", en: "Regenerate" },
  preparingReport: { tr: "Rapor hazırlanıyor…", en: "Preparing report…" },
  thinking: { tr: "Asistan düşünüyor…", en: "Assistant is thinking…" },
  modelNote: {
    tr: "Model gemide çalışıyor; cevap 10–30 sn sürebilir.",
    en: "The model runs onboard; answers can take 10–30 s.",
  },
  selecting: { tr: "{id}{day} seçiliyor…", en: "Selecting {id}{day}…" },
  dayPart: { tr: ", {day}. gün", en: ", day {day}" },
  noData: { tr: "Asistanda {id}{day} için veri yok.", en: "The assistant has no data for {id}{day}." },
  notAvailable: { tr: "Asistan bu seçim için kullanılamıyor.", en: "The assistant is not available for this selection." },
  dataTag: { tr: "Asistan verisi: {id}{day}", en: "Assistant data: {id}{day}" },
  dataTagDay: { tr: " · {day}. gün", en: " · day {day}" },
  offline: { tr: "Asistan çevrim dışı", en: "Assistant offline" },
  sources: { tr: "Kaynaklar ({n})", en: "Sources ({n})" },
  srData: { tr: "Veri kaynağı:", en: "Data source:" },
  srDoc: { tr: "Belge kaynağı:", en: "Document source:" },
  status: { tr: "durum {s}", en: "status {s}" },
  chatTitle: { tr: "Sağlık asistanı", en: "Health assistant" },
  clear: { tr: "Temizle", en: "Clear" },
  chatIntro: {
    tr: "Sağlık verilerin hakkında sor. Asistan teşhis koymaz; karar desteği verir. (Asistan İngilizce cevap verir.)",
    en: "Ask about your health data. The assistant does not diagnose; it provides decision support.",
  },
  messageLabel: { tr: "Mesaj", en: "Message" },
  placeholder: { tr: "Mesajını yaz…", en: "Type your message…" },
  send: { tr: "Gönder", en: "Send" },
  stop: { tr: "Durdur", en: "Stop" },
  stopped: { tr: "Durduruldu.", en: "Stopped." },
  error: { tr: "Hata", en: "Error" },
  emptyAnswer: { tr: "Asistan boş cevap döndü.", en: "The assistant returned an empty answer." },
  apiError: { tr: "Asistan API hatası {status}", en: "Assistant API error {status}" },
  timeout: { tr: "Asistan {s} sn içinde cevap vermedi.", en: "The assistant did not answer within {s} s." },
  unreachable: { tr: "Asistan API'sine ulaşılamıyor ({url}).", en: "Assistant API unreachable ({url})." },
} satisfies Record<string, Record<Lang, string>>;

export type AssistantTextKey = keyof typeof TEXTS;
type Vars = Record<string, string | number>;

export function translate(key: AssistantTextKey, lang: Lang, vars?: Vars): string {
  return Object.entries(vars ?? {}).reduce((s, [k, v]) => s.split(`{${k}}`).join(String(v)), TEXTS[key][lang]);
}

/** React dışı kod (API istemcisi, sohbet hook'u) için: o anki arayüz dili. */
export const tx = (key: AssistantTextKey, vars?: Vars) => translate(key, currentLang(), vars);

/** Bileşenler için: dil değişince yeniden çizilir. */
export function useAssistantTexts() {
  const { lang } = useLang();
  return (key: AssistantTextKey, vars?: Vars) => translate(key, lang, vars);
}
