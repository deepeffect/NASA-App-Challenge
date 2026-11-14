/**
 * Dünya üssü ekranının ayarları. Ürün adı ve gösterilen ekip buradan değişir (kod değişmez).
 *
 * - Ürün adı: derleme sırasında `VITE_PRODUCT_NAME` verilirse o (iki dilde aynı), yoksa aşağıdaki varsayılan.
 * - DEMO_CREW: "Mürettebat" bölümünde büyük kartla gösterilen astronotlar. Varsayılan: veri setindeki
 *   her simülasyon deseninden ilk astronot (sağlıklı, akut atak, iyileşiyor, kronik, kötüleşiyor, hafif sorun).
 */
import type { Lang } from "../../shared/i18n";

const envName = (import.meta.env.VITE_PRODUCT_NAME as string | undefined)?.trim();

export const PRODUCT_NAME: Record<Lang, string> = envName
  ? { tr: envName, en: envName }
  : { tr: "Astronot Sağlık İzleme", en: "Astronaut Health Monitor" };

export const TEAM_NAME = "AI Gambit";
export const EVENT_NAME = "NASA Space Apps Challenge 2026";

export const DEMO_CREW: readonly string[] = ["A000", "A003", "A006", "A007", "A012", "A013"];

/** Canlı akışta gösterilen en fazla olay. */
export const FEED_LIMIT = 60;
/** Yeni olay gelince kartın / satırın vurgulu kaldığı süre. */
export const HIGHLIGHT_MS = 4000;
/** SSE'ye ek olarak bağlantı durumunun yoklanma aralığı (SSE koparsa da güncel kalsın). */
export const LINK_POLL_MS = 10_000;
/** Mürettebat listesinin yedek yenilenme aralığı (asıl tetikleyici SSE olaylarıdır). */
export const CREW_POLL_MS = 60_000;
