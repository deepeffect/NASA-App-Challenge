/**
 * Asistan API istemcisi (LLM ekibinin servisi, örn. http://192.168.1.12:8000).
 * Kural motoru, [D]/[K] kaynak etiketleri ve sayı doğrulayıcı o API'nin içindedir; burada sadece
 * çağırıp gösteriyoruz. Yerel model yavaş olabilir (10–30 sn) → uzun zaman aşımı.
 * Bu API'nin şeması bizim docs/openapi.json sözleşmemizin parçası değildir; tipler elle yazıldı
 * (kaynak: <ASSISTANT>/docs).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export const ASSISTANT_BASE: string = (import.meta.env.VITE_ASSISTANT_API_URL ?? "http://192.168.1.12:8000").replace(
  /\/+$/,
  "",
);
const ASTRONAUT_ID: string | undefined = import.meta.env.VITE_ASSISTANT_ASTRONAUT_ID || undefined;
export const ASSISTANT_TIMEOUT_MS = 180_000;

// ---- Tipler ------------------------------------------------------------------
export type DataSource = {
  type: "data";
  label: string;
  value?: number | string | null;
  unit?: string | null;
  status?: string | null;
};
export type KnowledgeSource = { type: "knowledge"; label: string; text?: string | null };
export type SourceRef = DataSource | KnowledgeSource;
export type Sources = Record<string, SourceRef>;

export interface AssistantChatResponse {
  intent?: string;
  answer?: string | null;
  report?: string | null;
  sources?: Sources;
  info?: Record<string, unknown>;
}
export interface AssistantAlert {
  level: string; // "RED" | "YELLOW"
  indicator: string;
  tag?: string;
  fallback: string;
  explanation?: string | null;
  sources?: Sources;
}
export interface AssistantAlertsResponse {
  alerts: AssistantAlert[];
}
export interface DailyReportResponse {
  report: string;
  sources?: Sources;
}
export interface AssistantHealth {
  ok: boolean;
  current?: string | null;
  loaded?: string[];
}

export class AssistantError extends Error {}

// ---- İstek ---------------------------------------------------------------------
async function call<T>(
  method: "GET" | "POST",
  path: string,
  opts: { query?: Record<string, string | boolean | undefined>; body?: unknown; signal?: AbortSignal; timeoutMs?: number } = {},
): Promise<T> {
  const url = new URL(ASSISTANT_BASE + path);
  const query = { astronaut_id: ASTRONAUT_ID, ...opts.query };
  for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== "") url.searchParams.set(k, String(v));

  const timeoutMs = opts.timeoutMs ?? ASSISTANT_TIMEOUT_MS;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  const onAbort = () => ctrl.abort();
  opts.signal?.addEventListener("abort", onAbort);
  try {
    const res = await fetch(url, {
      method,
      signal: ctrl.signal,
      headers: opts.body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
    const data: unknown = await res.json().catch(() => null);
    if (!res.ok) {
      const detail = data && typeof data === "object" && "detail" in data ? String((data as { detail: unknown }).detail) : "";
      throw new AssistantError(`Assistant API error ${res.status}${detail ? `: ${detail}` : ""}`);
    }
    return data as T;
  } catch (e) {
    if (e instanceof AssistantError) throw e;
    if (opts.signal?.aborted) throw e; // kullanıcı durdurdu
    if (ctrl.signal.aborted) throw new AssistantError(`The assistant did not answer within ${Math.round(timeoutMs / 1000)} s.`);
    throw new AssistantError(`Assistant API unreachable (${ASSISTANT_BASE}).`);
  } finally {
    clearTimeout(timer);
    opts.signal?.removeEventListener("abort", onAbort);
  }
}

export const assistantApi = {
  health: () => call<AssistantHealth>("GET", "/health", { timeoutMs: 5_000 }),
  chat: (message: string, signal?: AbortSignal) =>
    call<AssistantChatResponse>("POST", "/chat", { body: { message, astronaut_id: ASTRONAUT_ID }, signal }),
  alerts: () => call<AssistantAlertsResponse>("GET", "/alerts"),
  dailyReport: (force = false, signal?: AbortSignal) =>
    call<DailyReportResponse>("GET", "/daily_report", { query: { force: force || undefined }, signal }),
  reset: () => call<unknown>("POST", "/reset", { timeoutMs: 10_000 }),
};

// ---- Sorgular ------------------------------------------------------------------
export const assistantKeys = {
  health: ["assistant", "health"] as const,
  alerts: ["assistant", "alerts"] as const,
  report: ["assistant", "daily_report"] as const,
};

export function useAssistantHealth() {
  return useQuery({ queryKey: assistantKeys.health, queryFn: assistantApi.health, refetchInterval: 30_000, retry: false });
}

export function useAssistantAlerts() {
  return useQuery({ queryKey: assistantKeys.alerts, queryFn: assistantApi.alerts,
    staleTime: 5 * 60_000,
    retry: 1,
    refetchOnWindowFocus: false, // her çağrı LLM açıklamalarını yeniden üretir (yavaş)
  });
}

export function useDailyReport() {
  return useQuery({
    queryKey: assistantKeys.report,
    queryFn: ({ signal }) => assistantApi.dailyReport(false, signal),
    staleTime: 10 * 60_000,
    retry: 1,
  });
}

/** Raporu yeniden ürettir (force=true) ve önbelleği günceller. */
export function useRegenerateReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => assistantApi.dailyReport(true),
    onSuccess: (data) => qc.setQueryData(assistantKeys.report, data),
  });
}
