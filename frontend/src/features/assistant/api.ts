/**
 * Asistan API istemcisi (LLM ekibinin servisi, örn. http://192.168.1.12:8000).
 * Kural motoru, [D]/[K] kaynak etiketleri ve sayı doğrulayıcı o API'nin içindedir; burada sadece
 * çağırıp gösteriyoruz. Yerel model yavaş olabilir (10–30 sn) → uzun zaman aşımı.
 * Bu API'nin şeması bizim docs/openapi.json sözleşmemizin parçası değildir; tipler elle yazıldı
 * (kaynak: <ASSISTANT>/docs).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { tx } from "./texts";

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
  file?: string | null;
  current?: string | null;
  mission_day?: number | null;
  loaded?: string[];
}
export interface AssistantRecords {
  file?: string | null;
  astronauts: Record<string, { first_day: number; last_day: number; count?: number }>;
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
      throw new AssistantError(`${tx("apiError", { status: res.status })}${detail ? `: ${detail}` : ""}`);
    }
    return data as T;
  } catch (e) {
    if (e instanceof AssistantError) throw e;
    if (opts.signal?.aborted) throw e; // kullanıcı durdurdu
    if (ctrl.signal.aborted) throw new AssistantError(tx("timeout", { s: Math.round(timeoutMs / 1000) }));
    throw new AssistantError(tx("unreachable", { url: ASSISTANT_BASE }));
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
  records: () => call<AssistantRecords>("GET", "/records", { timeoutMs: 10_000 }),
  select: (astronautId: string, day: number) =>
    call<unknown>("POST", "/select", { body: { astronaut_id: astronautId, day }, timeoutMs: 30_000 }),
};

// ---- Astronot/gün seçimi -----------------------------------------------------------
/**
 * Asistan API'si sunucu tarafında tek bir "seçili astronot-gün" tutar (POST /select).
 * Sayfadaki astronot + zaman kaydırıcısının görev günü değişince seçim gönderilir; rapor/uyarı
 * sorgularının anahtarı seçime bağlıdır (eski seçimin cevabı ekranda kalmaz).
 * /records yoksa (eski API) veya alınamazsa seçim yapılmaz, kartlar API'nin varsayılanıyla çalışır.
 */
export type SelectionStatus = "syncing" | "ready" | "no_data" | "error";
export interface AssistantSelection {
  key: string;
  ready: boolean;
  status: SelectionStatus;
  astronautId: string;
  day: number | null;
  message?: string;
}

const SELECT_DEBOUNCE_MS = 400; // kaydırıcı sürüklenirken her gün için istek gitmesin

export function useAssistantSelection(astronautId: string, day: number | null | undefined): AssistantSelection {
  const qc = useQueryClient();
  const records = useQuery({ queryKey: assistantKeys.records, queryFn: assistantApi.records, staleTime: 5 * 60_000, retry: false });
  const rec = records.data?.astronauts?.[astronautId];
  const hasData = !!rec && day != null && day >= rec.first_day && day <= rec.last_day;
  const want = `${astronautId}@${day ?? "-"}`;
  const [done, setDone] = useState<{ key: string; error?: string } | null>(null);

  useEffect(() => {
    if (!hasData || day == null) return;
    let cancelled = false;
    const t = setTimeout(() => {
      assistantApi
        .select(astronautId, day)
        .then(() => {
          if (cancelled) return;
          setDone({ key: want });
          void qc.invalidateQueries({ queryKey: assistantKeys.health });
        })
        .catch((e: unknown) => {
          if (!cancelled) setDone({ key: want, error: e instanceof Error ? e.message : String(e) });
        });
    }, SELECT_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [hasData, astronautId, day, want, qc]);

  const base = { astronautId, day: day ?? null };
  if (records.isPending) return { ...base, key: want, ready: false, status: "syncing" };
  if (records.isError) return { ...base, key: "default", ready: true, status: "ready" }; // /records yok → seçimsiz
  if (!hasData) {
    return {
      ...base, key: want, ready: false, status: "no_data",
      message: tx("noData", { id: astronautId, day: day != null ? tx("dayPart", { day }) : "" }),
    };
  }
  if (done?.key !== want) return { ...base, key: want, ready: false, status: "syncing" };
  if (done.error) return { ...base, key: want, ready: false, status: "error", message: done.error };
  return { ...base, key: want, ready: true, status: "ready" };
}

// ---- Sorgular ------------------------------------------------------------------
export const assistantKeys = {
  health: ["assistant", "health"] as const,
  records: ["assistant", "records"] as const,
  alerts: (sel: string) => ["assistant", "alerts", sel] as const,
  report: (sel: string) => ["assistant", "daily_report", sel] as const,
};

export function useAssistantHealth() {
  return useQuery({ queryKey: assistantKeys.health, queryFn: assistantApi.health, refetchInterval: 30_000, retry: false });
}

export function useAssistantAlerts(sel: AssistantSelection) {
  return useQuery({
    queryKey: assistantKeys.alerts(sel.key),
    queryFn: assistantApi.alerts,
    enabled: sel.ready,
    staleTime: 5 * 60_000,
    retry: 1,
    refetchOnWindowFocus: false, // her çağrı LLM açıklamalarını yeniden üretir (yavaş)
  });
}

export function reportQuery(sel: AssistantSelection) {
  return {
    queryKey: assistantKeys.report(sel.key),
    queryFn: ({ signal }: { signal: AbortSignal }) => assistantApi.dailyReport(false, signal),
    staleTime: 10 * 60_000,
  };
}

export function useDailyReport(sel: AssistantSelection) {
  return useQuery({ ...reportQuery(sel), enabled: sel.ready, retry: 1 });
}

/** Raporu yeniden ürettir (force=true) ve önbelleği günceller. */
export function useRegenerateReport(sel: AssistantSelection) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => assistantApi.dailyReport(true),
    onSuccess: (data) => qc.setQueryData(assistantKeys.report(sel.key), data),
  });
}
