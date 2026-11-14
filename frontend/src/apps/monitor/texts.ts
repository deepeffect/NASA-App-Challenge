/**
 * Dünya ekranının arayüz metinleri (TR/EN) ve biçimleyiciler. Sağlıkla ilgili metinler (durum, alt başlık,
 * check-in özeti, ölçüm etiketleri) backend'den seçili dilde gelir; burada sadece ekranın kendi metinleri var.
 */
import { useCallback } from "react";

import { type Lang, useLang } from "../../shared/i18n";

const T = {
  earthBase: { tr: "Dünya üssü", en: "Earth base" },
  readOnly: { tr: "salt okunur", en: "read-only" },
  logout: { tr: "Çıkış", en: "Log out" },
  themeDark: { tr: "Koyu tema", en: "Dark theme" },
  themeLight: { tr: "Açık tema", en: "Light theme" },
  language: { tr: "Dil", en: "Language" },
  loading: { tr: "Yükleniyor…", en: "Loading…" },
  retry: { tr: "Tekrar dene", en: "Try again" },
  footer: { tr: "{event} için {team} tarafından geliştirildi", en: "Built by {team} for {event}" },
  simNote: {
    tr: "Simüle veri. Aralıklar simüle veri setinden alınmıştır, tıbbi doğrulama yapılmamıştır.",
    en: "Simulated data. Ranges come from the simulated dataset and are not medically verified.",
  },

  // giriş
  loginTitle: { tr: "Dünya üssü girişi", en: "Earth base log in" },
  loginIntro: {
    tr: "Bu ekran salt okunurdur: gemiden downlink ile gelen, gemide gizlilik filtresinden geçmiş veriyi gösterir.",
    en: "This screen is read-only: it shows data that arrived from the ship by downlink, filtered for privacy on the ship.",
  },
  id: { tr: "Kimlik", en: "ID" },
  password: { tr: "Şifre", en: "Password" },
  login: { tr: "Giriş yap", en: "Log in" },
  loggingIn: { tr: "Giriş yapılıyor…", en: "Logging in…" },
  enterId: { tr: "Kimlik girin.", en: "Enter an ID." },
  demoLogin: {
    tr: "Bu bir prototip için demo girişidir. Gerçek bir şifre girmeyin.",
    en: "This is a demo login for a prototype. Do not enter a real password.",
  },
  serverDown: { tr: "Dünya sunucusuna ulaşılamıyor.", en: "Cannot reach the Earth server." },

  // bağlantı çubuğu
  shipLink: { tr: "Gemi bağlantısı", en: "Ship link" },
  connected: { tr: "bağlı", en: "connected" },
  disconnected: { tr: "bağlantı yok", en: "no link" },
  notConfigured: { tr: "ayarlı değil (SHIP_URL)", en: "not configured (SHIP_URL)" },
  lastContact: { tr: "son temas {ago}", en: "last contact {ago}" },
  neverContact: { tr: "henüz temas yok", en: "no contact yet" },
  queued: { tr: "kuyrukta {n} olay", en: "{n} events queued" },
  lightDelay: { tr: "Işık gecikmesi (simüle): {min} dk", en: "Light delay (simulated): {min} min" },
  demoDelay: { tr: "demo gecikmesi {s} sn", en: "demo delay {s} s" },
  lightDelayHint: {
    tr: "Gerçek görevde gemiden Dünya'ya bir mesaj bu kadar sürer. Demo veriyi bu süre kadar bekletmez.",
    en: "On a real mission a message from the ship takes this long to reach Earth. The demo does not hold data that long.",
  },
  linkDownTitle: { tr: "Bağlantı yok, son bilinen durum: {time}", en: "No link, last known state: {time}" },
  linkDownText: {
    tr: "Gemiden veri gelmiyor. Ekran son alınan veriyle çalışmaya devam ediyor; bağlantı gelince akış kaldığı yerden sürer.",
    en: "No data is arriving from the ship. The screen keeps showing the last data received; the feed resumes where it left off when the link returns.",
  },
  earthDownTitle: { tr: "Dünya sunucusuna ulaşılamıyor, son bilinen durum: {time}", en: "Cannot reach the Earth server, last known state: {time}" },
  earthDownText: {
    tr: "Bu ekran son alınan veriyi gösteriyor ve sunucuya yeniden bağlanmayı deniyor.",
    en: "This screen shows the last data received and keeps trying to reconnect.",
  },
  syncing: { tr: "Gemiden ilk veri bekleniyor…", en: "Waiting for the first data from the ship…" },
  secondsAgo: { tr: "{n} sn önce", en: "{n} s ago" },
  minutesAgo: { tr: "{n} dk önce", en: "{n} min ago" },
  hoursAgo: { tr: "{n} sa önce", en: "{n} h ago" },
  justNow: { tr: "şimdi", en: "just now" },

  // bölümler
  crewTitle: { tr: "Mürettebat", en: "Crew" },
  crewIntro: { tr: "Bugünün durumu, 30 günlük skor ve alanlar", en: "Today's status, 30-day score and areas" },
  groundTitle: { tr: "Yer desteği", en: "Ground support" },
  groundIntro: {
    tr: "Görünür ölçümlerine göre yer desteği gereken astronotlar. Paylaşılmamış ruh hali ve stres bu listeyi etkilemez.",
    en: "Astronauts who need ground support based on their visible readings. Unshared mood and stress do not affect this list.",
  },
  groundNone: { tr: "Bugün yer desteği gereken astronot yok.", en: "No astronaut needs ground support today." },
  groundFarOut: { tr: "Çok dışında olan ölçümler", en: "Readings far out of range" },
  healthyRange: { tr: "sağlıklı {range}", en: "healthy {range}" },
  allTitle: { tr: "Tüm astronotlar", en: "All astronauts" },
  feedTitle: { tr: "Canlı akış", en: "Live feed" },
  feedIntro: { tr: "Gemiden gelen olaylar, yeniden eskiye", en: "Events from the ship, newest first" },
  feedEmpty: { tr: "Henüz olay yok. Gemide bir check-in tamamlanınca burada görünür.", en: "No events yet. They appear here when a check-in is completed on the ship." },
  feedCount: { tr: "Son {n} olay · toplam {total}", en: "Last {n} events · {total} in total" },

  // kart
  score: { tr: "sağlık skoru", en: "health score" },
  missionDay: { tr: "görev günü {n}", en: "mission day {n}" },
  ageSex: { tr: "{age} yaş · {sex}", en: "{age} y · {sex}" },
  groundFlag: { tr: "Yer desteği gerekli", en: "Ground support needed" },
  lastCheckin: { tr: "Son check-in", en: "Last check-in" },
  sharing: { tr: "Paylaşım", en: "Sharing" },
  noCheckin: { tr: "bugün yok", en: "none today" },
  timeUnknown: { tr: "saat bilinmiyor", en: "time unknown" },
  shipTimeShort: { tr: "{time} gemi saati", en: "{time} ship time" },
  sparkLabel: {
    tr: "30 günlük sağlık skoru: ilk gün {first}, bugün {last}, en düşük {min}",
    en: "30-day health score: first day {first}, today {last}, lowest {min}",
  },
  sparkStart: { tr: "gün 1", en: "day 1" },
  sparkToday: { tr: "bugün", en: "today" },
  areasLabel: { tr: "Alanlar", en: "Areas" },
  levelOk: { tr: "aralıkta", en: "in range" },
  levelOut: { tr: "aralık dışında", en: "out of range" },
  levelFar: { tr: "çok dışında", en: "far out" },
  partlyHidden: { tr: "{n} ölçüm paylaşılmadı", en: "{n} readings not shared" },
  mainConcern: { tr: "ana endişe", en: "main concern" },
  legendOut: { tr: "Aralık dışında", en: "Out of range" },
  legendFar: { tr: "Çok dışında", en: "Far out" },
  legendHidden: { tr: "Paylaşılmadı", en: "Not shared" },
  legendConcern: { tr: "Ana endişe", en: "Main concern" },
  loadError: { tr: "Veri alınamadı.", en: "Could not load data." },
  noData: { tr: "Bu astronotun verisi yok.", en: "No data for this astronaut." },

  // paylaşım seviyeleri (Dünya'nın gözünden)
  share_none: { tr: "Check-in yok", en: "No check-in" },
  share_private: { tr: "Gizli tuttu", en: "Kept private" },
  share_scores: { tr: "Sadece skorlar", en: "Scores only" },
  share_full: { tr: "Her şey", en: "Everything" },

  // alanlar (kısa)
  dom_exposure: { tr: "Ortam", en: "Environment" },
  dom_immune: { tr: "Bağışıklık", en: "Immune" },
  dom_bone_muscle: { tr: "Kemik-kas", en: "Bone, muscle" },
  dom_cardiovascular: { tr: "Kalp", en: "Heart" },
  dom_behavioral: { tr: "Davranış", en: "Behaviour" },

  // tüm astronotlar
  search: { tr: "Kimlik ara", en: "Search ID" },
  searchPh: { tr: "örn. A042", en: "e.g. A042" },
  filterStatus: { tr: "Durum", en: "Status" },
  filterMission: { tr: "Görev", en: "Mission" },
  sortBy: { tr: "Sıralama", en: "Sort" },
  all: { tr: "Hepsi", en: "All" },
  sortScoreAsc: { tr: "Skor: düşükten yükseğe", en: "Score: low to high" },
  sortScoreDesc: { tr: "Skor: yüksekten düşüğe", en: "Score: high to low" },
  sortId: { tr: "Kimlik", en: "ID" },
  shown: { tr: "{n} / {total} astronot", en: "{n} of {total} astronauts" },
  noMatch: { tr: "Filtreye uyan astronot yok.", en: "No astronaut matches the filter." },
  colId: { tr: "Kimlik", en: "ID" },
  colMission: { tr: "Görev", en: "Mission" },
  colStatus: { tr: "Durum", en: "Status" },
  colScore: { tr: "Skor", en: "Score" },
  colNote: { tr: "Özet", en: "Summary" },
  colGround: { tr: "Yer desteği", en: "Ground" },
  colCheckin: { tr: "Check-in", en: "Check-in" },
  yes: { tr: "Gerekli", en: "Needed" },

  // akış
  ev_checkin_completed: { tr: "Check-in tamamlandı", en: "Check-in completed" },
  ev_checkin_shared: { tr: "Check-in paylaşıldı: {level}", en: "Check-in shared: {level}" },
  ev_action_done: { tr: "Öneri yapıldı: {title}", en: "Advice done: {title}" },
  ev_action_undone: { tr: "Öneri işareti kaldırıldı: {title}", en: "Advice unmarked: {title}" },
  ev_action_masked: { tr: "Bir öneri işaretlendi (ayrıntı paylaşılmadı)", en: "An advice item was marked (details not shared)" },
  ev_day_snapshot: { tr: "Gün verisi güncellendi", en: "Day data updated" },
  ev_link_down: { tr: "Gemi bağlantısı koptu", en: "Ship link lost" },
  ev_link_up: { tr: "Gemi bağlantısı geri geldi", en: "Ship link restored" },
  evDay: { tr: "gün {day} · görev günü {mission}", en: "day {day} · mission day {mission}" },
  evShip: { tr: "Gemi", en: "Ship" },
  evEarth: { tr: "Dünya", en: "Earth" },
  evTransit: { tr: "yolda {s} sn", en: "{s} s in transit" },
  evLinkNote: { tr: "Ekran saati {time}", en: "Screen time {time}" },
} as const;

export type MonitorTextKey = keyof typeof T;
export type TFn = (key: MonitorTextKey, vars?: Record<string, string | number>) => string;

export function translate(lang: Lang, key: MonitorTextKey, vars?: Record<string, string | number>): string {
  let s: string = T[key][lang];
  for (const [k, v] of Object.entries(vars ?? {})) s = s.replaceAll(`{${k}}`, String(v));
  return s;
}

export function useT(): { t: TFn; lang: Lang; locale: string } {
  const { lang } = useLang();
  const t = useCallback<TFn>((key, vars) => translate(lang, key, vars), [lang]);
  return { t, lang, locale: lang === "tr" ? "tr-TR" : "en-GB" };
}

// ---------------------------------------------------------------- biçimleyiciler
export function fmtTime(iso: string | null | undefined, locale: string, seconds = false): string {
  if (!iso) return "–";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "–";
  return d.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit", ...(seconds ? { second: "2-digit" } : {}) });
}

export function fmtAgo(iso: string | null | undefined, now: number, t: TFn): string {
  if (!iso) return "–";
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 2) return t("justNow");
  if (s < 90) return t("secondsAgo", { n: s });
  const m = Math.round(s / 60);
  if (m < 90) return t("minutesAgo", { n: m });
  return t("hoursAgo", { n: Math.round(m / 60) });
}

export function fmtSeconds(sec: number, locale: string): string {
  return sec.toLocaleString(locale, { maximumFractionDigits: sec < 10 ? 1 : 0 });
}

export const shareKey = (s: string | null | undefined): MonitorTextKey =>
  s === "private" ? "share_private" : s === "scores" ? "share_scores" : s === "full" ? "share_full" : "share_none";

export const domainKey = (d: string): MonitorTextKey | null =>
  (`dom_${d}` in T ? (`dom_${d}` as MonitorTextKey) : null);
