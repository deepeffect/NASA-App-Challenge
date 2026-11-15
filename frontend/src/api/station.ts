/**
 * Yeni mimarinin (gemi /me, Dünya /monitor) tipli API istemcisi. Tipler `npm run gen:api` ile üretilir.
 *
 * - Her isteğe `lang` açıkça eklenir (seçili arayüz dili).
 * - Token sekme oturumunda saklanır (sessionStorage); giriş ekranı `login()` ile alır.
 * - Hatalar `{detail, code}` biçimindedir → `StationApiError`.
 * - Backend frontend'i kendisi servis ettiğinde adres aynıdır (VITE_API_BASE_URL boş derlenir).
 */
import { fetchEventSource } from "@microsoft/fetch-event-source";

import { currentLang } from "../shared/i18n";
import { API_BASE } from "./client";
import type { components } from "./types";

type S = components["schemas"];
export type StationInfo = S["StationInfo"];
export type StationRole = StationInfo["role"];
export type AuthHint = S["AuthHint"];
export type LoginResponse = S["LoginResponse"];
export type PrincipalInfo = S["PrincipalInfo"];
export type PersonalOverview = S["PersonalOverview"];
export type StripDay = S["StripDay"];
export type DayView = S["DayView"];
export type ReadingView = S["ReadingView"];
export type TodoItemView = S["TodoItemView"];
export type CheckinState = S["CheckinState"];
export type CheckinTurnResponse = S["CheckinTurnResponse"];
export type ShareLevel = S["CheckinShareRequest"]["level"];
export type ActionDoneResponse = S["ActionDoneResponse"];
export type PresenceResponse = S["PresenceResponse"];
export type TerminalStatus = S["TerminalStatus"];
export type PersonalCatalog = S["PersonalCatalogResponse"];
export type MonitorCrewResponse = S["MonitorCrewResponse"];
export type MonitorDay = S["MonitorDay"];
export type LinkStatus = S["LinkStatus"];
export type MonitorStreamEvent = S["MonitorStreamEvent"];
export type ChatEvent = { event: string; data: unknown };

const TOKEN_KEY = "ahm-token";

export const auth = {
  get token(): string | null {
    try {
      return sessionStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string | null) {
    try {
      if (token) sessionStorage.setItem(TOKEN_KEY, token);
      else sessionStorage.removeItem(TOKEN_KEY);
    } catch {
      /* depolama kapalı */
    }
  },
};

export class StationApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  constructor(status: number, detail: string, code: string | null) {
    super(detail);
    this.status = status;
    this.code = code;
  }
}

function url(path: string, query: Record<string, string | number | boolean | undefined> = {}): string {
  const u = new URL(API_BASE + path, window.location.origin);
  u.searchParams.set("lang", currentLang());
  for (const [k, v] of Object.entries(query)) if (v !== undefined) u.searchParams.set(k, String(v));
  return u.toString();
}

async function call<T>(method: string, path: string, body?: unknown, query?: Record<string, string | number | boolean | undefined>): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", "Accept-Language": currentLang() };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = auth.token;
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(url(path, query), { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
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
  return (await res.json()) as T;
}

export const stationApi = {
  // ---- iki istasyon
  station: () => call<StationInfo>("GET", "/api/station"),
  hint: () => call<AuthHint>("GET", "/api/auth/hint"),
  login: async (id: string, password: string) => {
    const r = await call<LoginResponse>("POST", "/api/auth/login", { id, password });
    auth.set(r.token);
    return r;
  },
  logout: () => auth.set(null),
  whoami: () => call<PrincipalInfo>("GET", "/api/auth/me"),
  catalog: () => call<PersonalCatalog>("GET", "/api/catalog"),

  // ---- gemi: astronotun kendisi
  me: () => call<PersonalOverview>("GET", "/api/me"),
  day: (day: number) => call<DayView>("GET", `/api/me/days/${day}`),
  checkin: () => call<CheckinState>("GET", "/api/checkin"),
  checkinDay: (day: number) => call<CheckinState>("GET", `/api/checkin/days/${day}`),
  turn: (answer: string) => call<CheckinTurnResponse>("POST", "/api/checkin/turn", { answer }),
  share: (level: ShareLevel) => call<CheckinState>("POST", "/api/checkin/share", { level }),
  resetCheckin: () => call<CheckinState>("POST", "/api/checkin/reset"),
  actionDone: (code: string, done = true) => call<ActionDoneResponse>("POST", "/api/actions/done", { code, done }),
  /** Terminal sinyali (ekran açıkken düzenli aralıkla); `leaving` → çıkış: terminal beklemeden çevrimdışı. */
  presence: (leaving = false) => call<PresenceResponse>("POST", "/api/me/presence", leaving ? { leaving: true } : undefined),

  // ---- Dünya üssü
  crew: () => call<MonitorCrewResponse>("GET", "/api/monitor/crew"),
  astronaut: (id: string) => call<PersonalOverview>("GET", `/api/monitor/astronauts/${encodeURIComponent(id)}`),
  monitorDay: (id: string, day: number) => call<MonitorDay>("GET", `/api/monitor/astronauts/${encodeURIComponent(id)}/days/${day}`),
  link: () => call<LinkStatus>("GET", "/api/link/status"),
};

/** Dünya: yerel SSE (/api/stream/monitor). EventSource başlık gönderemediği için token sorguda. Kapatma fonksiyonu döner. */
export function openMonitorStream(onEvent: (name: string, data: MonitorStreamEvent) => void): () => void {
  const es = new EventSource(url("/api/stream/monitor", { access_token: auth.token ?? "" }));
  for (const name of ["event", "link"]) es.addEventListener(name, (e) => onEvent(name, JSON.parse((e as MessageEvent).data)));
  return () => es.close();
}

/** Gemi: "Asistana sor" (POST /api/chat, SSE). */
export function chat(messages: { role: "user" | "assistant"; content: string }[], onEvent: (e: ChatEvent) => void, signal?: AbortSignal) {
  return fetchEventSource(url("/api/chat"), {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${auth.token ?? ""}` },
    body: JSON.stringify({ messages, lang: currentLang() }),
    signal,
    openWhenHidden: true,
    onmessage: (m) => onEvent({ event: m.event, data: m.data ? JSON.parse(m.data) : null }),
    onerror: (err) => {
      throw err; // yeniden deneme yok
    },
  });
}
