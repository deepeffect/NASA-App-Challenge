/**
 * Astronot ekranının veri katmanı: sorgu anahtarları, sorgular ve "Asistana sor" akışı.
 *
 * - Bütün anahtarlar `["personal", …]` altındadır. Giriş gerektiren sorgular ve yazma istekleri oturuma özel
 *   sorgu istemcisinde çalışır (PersonalApp → `newSessionClient`); çıkışta ve oturum bitince istemciyle birlikte
 *   atılır (başka bir astronot aynı sekmede giriş yaparsa öncekinin verisini görmesin).
 * - Backend metinleri isteğin dilinde döner, bu yüzden dil anahtarın parçasıdır: TR/EN değişince yeniden istenir.
 * - Hiçbir kural burada hesaplanmaz; gelen `DayView` / `CheckinState` aynen gösterilir.
 */
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { keepPreviousData, type QueryClient, useQuery } from "@tanstack/react-query";

import { API_BASE, type EmergencyNotice, type SSEDone, type SSEError, type SSEToken, type SSEToolCall, type SSEToolResult } from "../../api/client";
import { auth, StationApiError, stationApi } from "../../api/station";
import { currentLang, type Lang } from "../../shared/i18n";

export const qk = {
  hint: (lang: Lang) => ["personal", "hint", lang] as const,
  me: (lang: Lang) => ["personal", "me", lang] as const,
  catalog: (lang: Lang) => ["personal", "catalog", lang] as const,
  day: (day: number, lang: Lang) => ["personal", "day", day, lang] as const,
  dayAny: (day: number) => ["personal", "day", day] as const,
  checkin: (day: number, lang: Lang) => ["personal", "checkin", day, lang] as const,
  checkinAny: (day: number) => ["personal", "checkin", day] as const,
  presence: () => ["personal", "presence"] as const,
};

export const isUnauthorized = (e: unknown): boolean => e instanceof StationApiError && e.status === 401;

/** 4xx hataları tekrar denenmez (yanlış istek, oturum yok); ağ ve 5xx hataları iki kez denenir. */
const retry = (count: number, e: unknown) => !(e instanceof StationApiError && e.status < 500) && count < 2;

/**
 * Bir değişiklikten (cevap, paylaşım, "Yaptım") sonra: cevap seçili dilde gelir ve o dilin önbelleğine yazılır;
 * diğer dilin eski kopyası silinir ki dil değişince bayat durum görünmesin.
 */
export function dropOtherLanguages(qc: QueryClient, prefix: readonly unknown[], lang: Lang): void {
  qc.removeQueries({ queryKey: prefix, predicate: (q) => q.queryKey[q.queryKey.length - 1] !== lang });
}

/** Herkese açık (giriş gerektirmez): uygulamanın istemcisinde tutulur, oturum bitince silinmez. */
export function useHint(lang: Lang) {
  return useQuery({ queryKey: qk.hint(lang), queryFn: stationApi.hint, retry: 1, staleTime: Infinity });
}

/** Herkese açık (giriş gerektirmez): uygulamanın istemcisinde tutulur, oturum bitince silinmez. */
export function useCatalog(lang: Lang) {
  return useQuery({ queryKey: qk.catalog(lang), queryFn: stationApi.catalog, retry, staleTime: Infinity, placeholderData: keepPreviousData });
}

/**
 * Giriş yapan astronotun özeti. Dil değişince yeni dilin cevabı gelene kadar eldeki görünüm kalır.
 * Sadece oturumun istemcisi altında çağrılır (PersonalApp → Session): "önceki veri" oturumlar arasında taşınmaz.
 */
export function useOverview(lang: Lang) {
  return useQuery({ queryKey: qk.me(lang), queryFn: stationApi.me, retry, placeholderData: keepPreviousData });
}

/** Bir günün görünümü. Yüklenirken önceki günün verisi döner; `data.day` ile seçili günü karşılaştırın. */
export function useDay(day: number | undefined, lang: Lang) {
  return useQuery({
    queryKey: qk.day(day ?? 0, lang),
    queryFn: () => stationApi.day(day as number),
    enabled: day !== undefined,
    retry,
    placeholderData: keepPreviousData,
  });
}

/** Bir günün check-in'i: bugün etkileşimli, geçmiş günler salt okunur (backend `editable` ile söyler). */
export function useCheckin(day: number | undefined, lang: Lang) {
  return useQuery({
    queryKey: qk.checkin(day ?? 0, lang),
    queryFn: () => stationApi.checkinDay(day as number),
    enabled: day !== undefined,
    retry,
  });
}

/**
 * Terminal varlığı: ekran açıkken gemiye sinyal (`POST /api/me/presence`). İlk sinyal girişte hemen, sonra gemi
 * cevabındaki aralıkla (PRESENCE_HEARTBEAT_SECONDS, varsayılan 30 sn); sekme arka plandayken de sürer (ekran açık =
 * terminal çevrimiçi), sekme yeniden görünür olunca ve ağ geri gelince hemen. Dünya sadece çevrimiçi / çevrimdışı ve
 * son görülmeyi görür; ne yazıldığını görmez. Sonucu ekranda gösterilmez.
 *
 * Sorgu olarak yazıldı: aralık, odak / yeniden bağlanma ve oturum yalıtımı hazır gelir — çıkışta oturumun
 * istemcisiyle birlikte durur, 401 dönerse Session'ın önbellek dinleyicisi girişe döndürür.
 */
export function useTerminalPresence(): void {
  useQuery({
    queryKey: qk.presence(),
    queryFn: () => stationApi.presence(),
    refetchInterval: (q) => (q.state.data?.interval_seconds ?? 30) * 1000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: "always",
    refetchOnReconnect: "always",
    staleTime: 0,
    retry,
  });
}

// ----------------------------------------------------------------------------- Asistana sor (POST /api/chat, SSE)
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatHandlers {
  onToken: (text: string) => void;
  onToolCall: (call: SSEToolCall) => void;
  onToolResult: (result: SSEToolResult) => void;
  /** Acil belirti: kural tabanlıdır, modelden önce gelir ve model kapalıyken de gelir. */
  onEmergency: (notice: EmergencyNotice) => void;
  onDone: (done: SSEDone) => void;
  onError: (error: SSEError) => void;
}

/**
 * Sohbet akışı. Akış başlamadan dönen hatalar (401, 403, 422) `StationApiError` olarak fırlatılır;
 * akış içindeki hatalar `onError` ile gelir. Sunucu akışı kapatınca söz çözülür. Yeniden deneme yoktur.
 */
export async function streamChat(messages: ChatMessage[], handlers: ChatHandlers, signal: AbortSignal): Promise<void> {
  const lang = currentLang();
  const url = new URL(`${API_BASE}/api/chat`, window.location.origin);
  url.searchParams.set("lang", lang);
  await fetchEventSource(url.toString(), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      "Accept-Language": lang,
      Authorization: `Bearer ${auth.token ?? ""}`,
    },
    body: JSON.stringify({ messages, lang }),
    signal,
    openWhenHidden: true,
    async onopen(res) {
      if (res.ok && (res.headers.get("content-type") ?? "").includes("text/event-stream")) return;
      let detail = res.statusText;
      let code: string | null = null;
      try {
        const body = await res.json();
        if (typeof body.detail === "string") detail = body.detail;
        code = body.code ?? null;
      } catch {
        /* gövde JSON değil */
      }
      if (res.status === 401) auth.set(null);
      throw new StationApiError(res.status, detail, code);
    },
    onmessage(message) {
      if (!message.event || !message.data) return; // canlı tutma (ping) satırları
      const data: unknown = JSON.parse(message.data);
      switch (message.event) {
        case "token":
          handlers.onToken((data as SSEToken).text);
          break;
        case "tool_call":
          handlers.onToolCall(data as SSEToolCall);
          break;
        case "tool_result":
          handlers.onToolResult(data as SSEToolResult);
          break;
        case "emergency":
          handlers.onEmergency(data as EmergencyNotice);
          break;
        case "done":
          handlers.onDone(data as SSEDone);
          break;
        case "error":
          handlers.onError(data as SSEError);
          break;
        default: // meta, thinking: bu ekranda gösterilmez
      }
    },
    onerror(error) {
      throw error; // kütüphanenin otomatik yeniden denemesini kapat
    },
  });
}
