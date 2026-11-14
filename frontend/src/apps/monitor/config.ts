/**
 * Dünya üssü ekranının ayarları. Ürün adı ve gösterilen ekip buradan değişir (kod değişmez).
 *
 * - Ürün adı: derleme sırasında `VITE_PRODUCT_NAME` verilirse o (iki dilde aynı), yoksa aşağıdaki varsayılan.
 * - MISSION / DEMO_CREW: hikâye Mars'a giden tek bir gemi; mürettebat aynı görevden (Mars_Transit) seçildi.
 *   `npm run find-demo` her desenden bir temsilci önerir (en az biri 30 günde Normal → Dikkat → Rahatsız geçer).
 *   İlk kişi smoke testinde check-in yapan astronottur (bugün Normal, öneri listesi boş değil).
 */
import type { Lang } from "../../shared/i18n";

// import.meta.env Vite dışında (smoke testi Node'da bu dosyayı okur) tanımsızdır
const envName = (import.meta.env?.VITE_PRODUCT_NAME as string | undefined)?.trim();

export const PRODUCT_NAME: Record<Lang, string> = envName
  ? { tr: envName, en: envName }
  : { tr: "Astronot Sağlık İzleme", en: "Astronaut Health Monitor" };

export const TEAM_NAME = "AI Gambit";
export const EVENT_NAME = "NASA Space Apps Challenge 2026";

/** Geminin görevi (görev çubuğu). Mürettebat bu görevin astronotlarıdır. */
export const MISSION = { id: "Mars_Transit", name: { tr: "Mars transferi", en: "Mars transfer" } as Record<Lang, string> };

/**
 * A168 sağlıklı (smoke astronotu) · A076 hafif sorun · A115 iyileşiyor · A117 akut atak (gün 1 → 23 → 27 Normal → Dikkat
 * → Rahatsız) · A022 kötüleşiyor (gün 1 → 20 → 27) · A007 kronik. Kaynak: npm run find-demo (Mars_Transit).
 */
export const DEMO_CREW: readonly string[] = ["A168", "A076", "A115", "A117", "A022", "A007"];

/** Canlı akışta gösterilen en fazla olay. */
export const FEED_LIMIT = 60;
/** "Sadece mürettebat" açıkken süzülmek üzere alınan son olay sayısı (mürettebat dışı olaylar arada kalmasın). */
export const FEED_CREW_FETCH = 300;
/** Yeni olay gelince kartın / satırın vurgulu kaldığı süre. */
export const HIGHLIGHT_MS = 4000;
/** SSE'ye ek olarak bağlantı durumunun yoklanma aralığı (SSE koparsa da güncel kalsın). */
export const LINK_POLL_MS = 10_000;
/** Mürettebat listesinin yedek yenilenme aralığı (asıl tetikleyici SSE olaylarıdır). */
export const CREW_POLL_MS = 60_000;
/** Mürettebat kartındaki "Aktif" rozeti: son etkinlik (gemi saati) bu süreden yeniyse. */
export const ACTIVE_WINDOW_MS = 10 * 60_000;
