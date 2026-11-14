/**
 * Dünya ekranının veri katmanı. Her şey bu istasyonun (Dünya) backend'inden, earth.db'den okunur;
 * gemiye doğrudan istek atılmaz. Uçlar: src/api/station.ts (`stationApi.*`) + burada olay listesi
 * (`GET /api/monitor/events`) ve canlı akışın adresi.
 *
 * Sorgu anahtarları dili içerir: metinler backend'den seçili dilde gelir.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { API_BASE } from "../../api/client";
import { auth, StationApiError, stationApi } from "../../api/station";
import type { components } from "../../api/types";
import { currentLang, useLang } from "../../shared/i18n";
import { CREW_POLL_MS, LINK_POLL_MS } from "./config";

type S = components["schemas"];
export type MonitorEvent = S["MonitorEvent"];
export type MonitorEventsResponse = S["MonitorEventsResponse"];
export type MonitorEventType = MonitorEvent["type"];
export type MonitorCrewMember = S["MonitorCrewMember"];
export type AreaScoreView = S["AreaScoreView"];

function url(path: string, query: [string, string | number][] = []): string {
  const u = new URL(API_BASE + path, window.location.origin);
  u.searchParams.set("lang", currentLang());
  for (const [k, v] of query) u.searchParams.append(k, String(v));
  return u.toString();
}

export interface EventsQuery {
  limit?: number;
  astronautId?: string;
  types?: MonitorEventType[];
  beforeSeq?: number;
}

export async function fetchEvents(q: EventsQuery = {}): Promise<MonitorEventsResponse> {
  const query: [string, string | number][] = [];
  if (q.limit) query.push(["limit", q.limit]);
  if (q.astronautId) query.push(["astronaut_id", q.astronautId]);
  for (const t of q.types ?? []) query.push(["type", t]);
  if (q.beforeSeq) query.push(["before_seq", q.beforeSeq]);
  const headers: Record<string, string> = { Accept: "application/json", "Accept-Language": currentLang() };
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`;
  const res = await fetch(url("/api/monitor/events", query), { headers });
  if (!res.ok) {
    let detail = res.statusText;
    let code: string | null = null;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : detail;
      code = j.code ?? null;
    } catch {
      /* gövde JSON değil */
    }
    if (res.status === 401) auth.set(null);
    throw new StationApiError(res.status, detail, code);
  }
  return (await res.json()) as MonitorEventsResponse;
}

/** Yerel SSE (/api/stream/monitor). EventSource başlık gönderemediği için token sorguda. */
export function monitorStreamUrl(): string {
  return url("/api/stream/monitor", [["access_token", auth.token ?? ""]]);
}

// ---------------------------------------------------------------- sorgular
export const qk = {
  all: ["monitor"] as const,
  link: () => ["monitor", "link"] as const,
  crew: (lang: string) => ["monitor", "crew", lang] as const,
  catalog: (lang: string) => ["monitor", "catalog", lang] as const,
  overview: (id: string, lang: string) => ["monitor", "overview", id, lang] as const,
  overviewAny: (id: string) => ["monitor", "overview", id] as const,
  day: (id: string, day: number, lang: string) => ["monitor", "day", id, day, lang] as const,
  dayAny: (id: string) => ["monitor", "day", id] as const,
  events: (limit: number) => ["monitor", "events", "feed", limit] as const,
  checkins: () => ["monitor", "events", "checkins"] as const,
  activity: (id: string) => ["monitor", "events", "activity", id] as const,
};

export const isUnauthorized = (e: unknown): boolean => e instanceof StationApiError && e.status === 401;
export const isNotFound = (e: unknown): boolean => e instanceof StationApiError && e.status === 404;

/** Kısa kesintilerde (Dünya sunucusu yeniden başlıyor) birkaç kez dene: 1, 2, 4 sn. İstemci hatasında (4xx) deneme. */
const retry = (n: number, e: unknown) => !(e instanceof StationApiError && e.status >= 400 && e.status < 500) && n < 3;
/** Yenilemede eski veri kalır; hiç veri gelmediyse sık yokla (kiosk kendini toparlasın). */
const keep = { placeholderData: keepPreviousData, retry } as const;
const pollUntilData = (normalMs: number | false) => (q: { state: { data: unknown; status: string } }) =>
  q.state.data === undefined && q.state.status === "error" ? 5_000 : normalMs;

export function useLinkStatus() {
  return useQuery({ queryKey: qk.link(), queryFn: stationApi.link, refetchInterval: LINK_POLL_MS, retry: 0, staleTime: 2_000 });
}

export function useCrew() {
  const { lang } = useLang();
  return useQuery({ queryKey: qk.crew(lang), queryFn: stationApi.crew, refetchInterval: pollUntilData(CREW_POLL_MS), ...keep });
}

export function useCatalog() {
  const { lang } = useLang();
  return useQuery({ queryKey: qk.catalog(lang), queryFn: stationApi.catalog, staleTime: Infinity, refetchInterval: pollUntilData(false), ...keep });
}

export function useOverview(id: string) {
  const { lang } = useLang();
  return useQuery({ queryKey: qk.overview(id, lang), queryFn: () => stationApi.astronaut(id), refetchInterval: pollUntilData(false), ...keep });
}

export function useMonitorDay(id: string, day: number | undefined) {
  const { lang } = useLang();
  return useQuery({
    queryKey: qk.day(id, day ?? 0, lang),
    queryFn: () => stationApi.monitorDay(id, day ?? 1),
    enabled: day !== undefined,
    refetchInterval: pollUntilData(false),
    ...keep,
  });
}

export function useFeedEvents(limit: number) {
  return useQuery({ queryKey: qk.events(limit), queryFn: () => fetchEvents({ limit }), refetchInterval: pollUntilData(false), ...keep });
}

/**
 * Etkinlik = astronotun kendi yaptığı: check-in tamamladı, paylaştı, öneriyi işaretledi. `day.snapshot` sayılmaz:
 * veri seti değişince gemi bütün günleri yeniden yayınlar, bu bir astronot etkinliği değildir.
 */
export const ACTIVITY_TYPES: MonitorEventType[] = ["checkin.completed", "checkin.shared", "action.done"];

/** Astronotun son etkinliği (yoksa null). Yeni olayda ["monitor", "events"] ile yenilenir. */
export function useLastActivity(id: string) {
  return useQuery({
    queryKey: qk.activity(id),
    queryFn: async () => (await fetchEvents({ astronautId: id, limit: 1, types: ACTIVITY_TYPES })).events[0] ?? null,
    refetchInterval: pollUntilData(false),
    ...keep,
  });
}

/** Her astronotun bugünkü son check-in'i (gemi saati). Snapshot'la gelenlerin olayı yoktur → saat bilinmiyor. */
export function useCheckinTimes() {
  return useQuery({
    queryKey: qk.checkins(),
    queryFn: async () => {
      const r = await fetchEvents({ limit: 500, types: ["checkin.completed"] });
      const out = new Map<string, MonitorEvent>();
      for (const e of r.events) if (e.astronaut_id && !out.has(e.astronaut_id)) out.set(e.astronaut_id, e); // yeniden eskiye
      return out;
    },
    refetchInterval: pollUntilData(false),
    ...keep,
  });
}
