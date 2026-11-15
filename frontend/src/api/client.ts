/**
 * Küçük, tipli API istemcisi. Tipler `npm run gen:api` ile ../docs/openapi.json'dan üretilir
 * (src/api/types.ts — elle düzenleme). Base URL: VITE_API_BASE_URL.
 */
import type { components, paths } from "./types";

type S = components["schemas"];

// ---- Sık kullanılan tipler (sözleşmeden) -----------------------------------
export type HealthResponse = S["HealthResponse"];
export type CatalogResponse = S["CatalogResponse"];
export type MetricInfo = S["MetricInfo"];
export type CrewResponse = S["CrewResponse"];
export type CrewMember = S["CrewMember"];
export type MissionInfo = S["MissionInfo"];
export type AstronautSummary = S["AstronautSummary"];
export type SystemScore = S["SystemScore"];
export type MetricSnapshot = S["MetricSnapshot"];
export type MetricSeriesResponse = S["MetricSeriesResponse"];
export type HealthEvent = S["HealthEvent"];
export type Contributor = S["Contributor"];
export type AlertListResponse = S["AlertListResponse"];
export type ExplainRequest = S["ExplainRequest"];
export type ExplainResponse = S["ExplainResponse"];
export type FeedbackRequest = S["FeedbackRequest"];
export type FeedbackResponse = S["FeedbackResponse"];
export type ShareResponse = S["ShareResponse"];
export type BriefingResponse = S["BriefingResponse"];
export type CheckinRequest = S["CheckinRequest"];
export type CheckinResponse = S["CheckinResponse"];
export type CheckinListResponse = S["CheckinListResponse"];
export type EmergencyNotice = S["EmergencyNotice"];
export type EmergencyCheckResponse = S["EmergencyCheckResponse"];
export type IngestReport = S["IngestReport"];
export type GroundReport = S["GroundReport"];
export type ChatRequest = S["ChatRequest"];
export type ChatMessage = S["ChatMessage"];
export type ChatEventName = S["ChatEventName"];
export type SSEMeta = S["SSEMeta"];
export type SSEToken = S["SSEToken"];
export type SSEThinking = S["SSEThinking"];
export type SSEToolCall = S["SSEToolCall"];
export type SSEToolResult = S["SSEToolResult"];
export type SSEDone = S["SSEDone"];
export type SSEError = S["SSEError"];

export type StatusColor = CrewMember["status"];
export type Severity = HealthEvent["severity"];
export type EventSource = HealthEvent["source"];
export type HealthSystem = HealthEvent["system"];
export type Lang = NonNullable<ExplainRequest["lang"]>;

export type AlertsQuery = NonNullable<paths["/api/alerts"]["get"]["parameters"]["query"]>;
export type MetricSeriesQuery = NonNullable<paths["/api/astronauts/{astronaut_id}/metrics"]["get"]["parameters"]["query"]>;

// ---- İstek altyapısı --------------------------------------------------------
export const API_BASE: string = (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

type QueryValue = string | number | boolean | null | undefined | readonly string[];
type Query = Record<string, QueryValue>;

export function buildUrl(path: string, query?: Query): string {
  const url = new URL(API_BASE + path, window.location.origin);
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v === null || v === undefined || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => url.searchParams.append(k, String(x)));
    else url.searchParams.set(k, String(v));
  }
  return url.toString();
}

async function request<T>(method: string, path: string, opts: { query?: Query; body?: unknown; form?: FormData } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    body = JSON.stringify(opts.body);
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(buildUrl(path, opts.query), { method, headers, body });
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* gövde JSON değil */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const enc = encodeURIComponent;

// ---- Endpoint'ler -----------------------------------------------------------
export const api = {
  health: () => request<HealthResponse>("GET", "/api/health"),
  catalog: () => request<CatalogResponse>("GET", "/api/metrics/catalog"),
  crew: (asOf?: string | null) => request<CrewResponse>("GET", "/api/crew", { query: { as_of: asOf } }),
  summary: (id: string, asOf?: string | null) =>
    request<AstronautSummary>("GET", `/api/astronauts/${enc(id)}/summary`, { query: { as_of: asOf } }),
  metricSeries: (id: string, q: MetricSeriesQuery) =>
    request<MetricSeriesResponse>("GET", `/api/astronauts/${enc(id)}/metrics`, { query: q }),
  checkins: (id: string, q: { days?: number; as_of?: string | null } = {}) =>
    request<CheckinListResponse>("GET", `/api/astronauts/${enc(id)}/checkins`, { query: q }),
  briefing: (id: string, q: { as_of?: string | null; lang?: Lang; refresh?: boolean } = {}) =>
    request<BriefingResponse>("GET", `/api/astronauts/${enc(id)}/briefing`, { query: q }),
  alerts: (q: AlertsQuery = {}) => request<AlertListResponse>("GET", "/api/alerts", { query: q as Query }),
  alert: (eventId: string, asOf?: string | null) =>
    request<HealthEvent>("GET", `/api/alerts/${enc(eventId)}`, { query: { as_of: asOf } }),
  explain: (eventId: string, body: Partial<ExplainRequest> = {}) =>
    request<ExplainResponse>("POST", `/api/alerts/${enc(eventId)}/explain`, { body }),
  feedback: (eventId: string, body: FeedbackRequest) =>
    request<FeedbackResponse>("POST", `/api/alerts/${enc(eventId)}/feedback`, { body }),
  share: (eventId: string, shareWithGround: boolean) =>
    request<ShareResponse>("PUT", `/api/alerts/${enc(eventId)}/share`, { body: { share_with_ground: shareWithGround } }),
  /** Kural tabanlı acil tarama (LLM'siz) — legacy sohbet harici asistan API'sine gittiğinde. */
  emergencyCheck: (text: string, lang?: Lang) =>
    request<EmergencyCheckResponse>("POST", "/api/emergency/check", { body: { text, lang } }),
  checkin: (body: CheckinRequest) => request<CheckinResponse>("POST", "/api/checkin", { body }),
  ingest: (file: File, q: { adapter?: string; astronaut_id?: string } = {}) => {
    const form = new FormData();
    form.append("file", file);
    return request<IngestReport>("POST", "/api/ingest", { form, query: q });
  },
  groundReport: (q: { as_of?: string | null; days?: number } = {}) =>
    request<GroundReport>("GET", "/api/ground-report", { query: q }),
};
