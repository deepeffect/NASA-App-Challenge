/**
 * Astronot ekranının (/me) kendi metinleri (TR/EN).
 *
 * Sadece ekranın çerçevesi buradadır: üst bar, giriş kartı, check-in ve sohbet kartının etiketleri, dipnot.
 * Sağlıkla ilgili her metin (durum, gerekçe, sorular, cevaplar, paylaşım açıklamaları, aktif mod satırı,
 * "Gemideki sağlık sorumlusu bilgilendirildi" kutusu) backend'den hazır gelir ve aynen gösterilir.
 * İngilizce metinler prototiple (frontend/reference/personal-artifact.html) aynıdır; farklı olan yerler
 * prototipin "bu cihazda" dediği yerlerdir: kayıt artık tarayıcıda değil gemidedir.
 */
import { useMemo } from "react";

import { type Lang, useLang } from "../../shared/i18n";

const T = {
  title: { tr: "Astronot Sağlık Kontrolü", en: "Astronaut Health Check" },
  logout: { tr: "Çıkış", en: "Log out" },
  language: { tr: "Dil", en: "Language" },
  allSolutions: { tr: "Tüm öz bakım çözümleri", en: "All self-care solutions" },

  // ---- giriş
  loginTitle: { tr: "Giriş", en: "Log in" },
  idLabel: { tr: "Kimlik", en: "ID" },
  pwLabel: { tr: "Şifre", en: "Password" },
  pwPlaceholder: { tr: "Kimliğinizle aynı", en: "Same as your ID" },
  loginButton: { tr: "Giriş yap", en: "Log in" },
  enterId: { tr: "Bir kimlik girin.", en: "Enter an ID." },
  demoNote: {
    tr: "Bu, prototip için bir demo girişidir. Gerçek bir şifre girmeyin.",
    en: "This is a demo login for a prototype. Do not enter a real password.",
  },
  serverDown: { tr: "Gemi sunucusuna ulaşılamıyor.", en: "Cannot reach the ship's server." },
  sessionEnded: { tr: "Oturumunuz sona erdi; yeniden giriş yapın.", en: "Your session has ended. Log in again." },

  // ---- genel
  loading: { tr: "Yükleniyor…", en: "Loading…" },
  loadError: { tr: "Veri yüklenemedi.", en: "Could not load the data." },
  retry: { tr: "Yeniden dene", en: "Try again" },
  detailsTitle: { tr: "Bu günün ayrıntıları", en: "Details for this day" },
  footnote: {
    tr: "{count} astronotun her biri için {days} günlük simüle veri. Öz bakım adımları prototip için temsilidir, tıbbi tavsiye değildir.",
    en: "Simulated data for {count} astronauts over {days} days each. The self-care steps are illustrative for a prototype and are not medical guidance.",
  },
  footnoteShort: {
    tr: "Simüle veri. Öz bakım adımları prototip için temsilidir, tıbbi tavsiye değildir.",
    en: "Simulated data. The self-care steps are illustrative for a prototype and are not medical guidance.",
  },

  // ---- günlük check-in
  checkinTitle: { tr: "Günlük check-in", en: "Daily check-in" },
  startOver: { tr: "Baştan başla", en: "Start over" },
  answerPlaceholder: { tr: "Cevabınızı yazın", en: "Type your answer" },
  answerDone: { tr: "Check-in tamamlandı", en: "Check-in complete" },
  answerLabel: { tr: "Cevabınız", en: "Your answer" },
  send: { tr: "Gönder", en: "Send" },
  flagged: { tr: "işaretlendi", en: "flagged" },
  shareQuestion: { tr: "Bu check-in Dünya ile paylaşılsın mı?", en: "Share this check-in with Earth?" },
  sharedLevel: { tr: "Dünya ile paylaşım: {level}", en: "Shared with Earth: {level}" },
  answersStay: {
    tr: "Cevaplarınız, sonunda paylaşmayı seçmediğiniz sürece gemide kalır.",
    en: "Your answers stay on the ship unless you choose to share them at the end.",
  },
  sendFailed: { tr: "Gönderilemedi. Lütfen yeniden cevaplayın.", en: "That did not go through. Please answer again." },
  pastNoCheckin: { tr: "Bu gün için kaydedilmiş bir check-in yok.", en: "No check-in was saved for this day." },
  pastReadOnly: {
    tr: "Check-in sadece bugün yapılır; geçmiş günler salt okunurdur.",
    en: "Check-ins are done for today only; past days are read-only.",
  },

  // ---- asistana sor
  askTitle: { tr: "Asistana sor", en: "Ask the assistant" },
  askIntro: {
    tr: "Kendi ölçümleriniz, yapılacaklarınız ve öz bakım adımları hakkında soru sorabilirsiniz. Asistan teşhis koymaz, karar desteği verir.",
    en: "Ask about your own readings, your to-do list and the self-care steps. The assistant does not diagnose; it supports your decisions.",
  },
  askPlaceholder: { tr: "Sorunuzu yazın", en: "Type your question" },
  askLabel: { tr: "Sorunuz", en: "Your question" },
  stop: { tr: "Durdur", en: "Stop" },
  askStays: { tr: "Bu sohbet gemide kalır, Dünya'ya gönderilmez.", en: "This chat stays on the ship; it is not sent to Earth." },
  askWriting: { tr: "Asistan yazıyor…", en: "The assistant is writing…" },
  askLooking: { tr: "Verilerinize bakılıyor…", en: "Looking at your data…" },
  askFailed: {
    tr: "Asistana ulaşılamadı. Uyarılar ve check-in çalışmaya devam eder.",
    en: "Could not reach the assistant. Alerts and the check-in keep working.",
  },
  askStopped: { tr: "Durduruldu.", en: "Stopped." },
  ungrounded: {
    tr: "Bu cevaptaki şu sayılar verilerinizle doğrulanamadı: {list}",
    en: "These numbers in the answer could not be checked against your data: {list}",
  },
  protocolPlaceholder: {
    tr: "Bu protokol metni yer tutucudur; tıbbi doğrulaması yapılmamıştır.",
    en: "This protocol text is a placeholder and has not been medically validated.",
  },
} as const;

export type PersonalTextKey = keyof typeof T;

export function translate(lang: Lang, key: PersonalTextKey, vars?: Record<string, string | number>): string {
  let s: string = T[key][lang];
  for (const [k, v] of Object.entries(vars ?? {})) s = s.replaceAll(`{${k}}`, String(v));
  return s;
}

/** Seçili dilde metin: `const { t, lang } = useT()`. */
export function useT() {
  const { lang, setLang } = useLang();
  return useMemo(
    () => ({ lang, setLang, t: (key: PersonalTextKey, vars?: Record<string, string | number>) => translate(lang, key, vars) }),
    [lang, setLang],
  );
}
