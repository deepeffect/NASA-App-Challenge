/** TanStack Query hook'ları. Tüm veri sorguları global `as_of` (zaman kaydırıcısı) alır. */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type AlertsQuery, type CheckinRequest, type ExplainRequest, type FeedbackRequest, type Lang } from "./client";

export const qk = {
  health: ["health"] as const,
  catalog: ["catalog"] as const,
  crew: (asOf: string | null) => ["crew", asOf] as const,
  summary: (id: string, asOf: string | null) => ["summary", id, asOf] as const,
  scores: (id: string, days: number, asOf: string | null) => ["scores", id, days, asOf] as const,
  series: (id: string, metric: string, days: number, asOf: string | null) => ["series", id, metric, days, asOf] as const,
  alerts: (q: AlertsQuery) => ["alerts", q] as const,
  briefing: (id: string, asOf: string | null, lang: Lang) => ["briefing", id, asOf, lang] as const,
  checkins: (id: string, asOf: string | null) => ["checkins", id, asOf] as const,
};

export function useHealth() {
  return useQuery({ queryKey: qk.health, queryFn: api.health, refetchInterval: 15_000 });
}

export function useCatalog() {
  return useQuery({ queryKey: qk.catalog, queryFn: api.catalog, staleTime: Infinity });
}

export function useCrew(asOf: string | null) {
  return useQuery({ queryKey: qk.crew(asOf), queryFn: () => api.crew(asOf), placeholderData: keepPreviousData });
}

export function useSummary(id: string, asOf: string | null) {
  return useQuery({
    queryKey: qk.summary(id, asOf),
    queryFn: () => api.summary(id, asOf),
    placeholderData: keepPreviousData,
  });
}

/**
 * Günlük skor geçmişi: `endDate` gününde biten `days` günlük pencere (endDate yokken sorgu beklemede kalır).
 * İlk çağrı sunucuda birkaç saniye sürebilir; sonrası önbellekten gelir.
 */
export function useScoreHistory(id: string, days: number, endDate: string | null) {
  return useQuery({
    queryKey: qk.scores(id, days, endDate),
    queryFn: () => api.scoreHistory(id, { days, as_of: endDate }),
    placeholderData: keepPreviousData,
    staleTime: 5 * 60_000,
    enabled: Boolean(id && endDate),
  });
}

export function useMetricSeries(id: string, metric: string, days: number, asOf: string | null) {
  return useQuery({
    queryKey: qk.series(id, metric, days, asOf),
    queryFn: () => api.metricSeries(id, { metric, days, as_of: asOf }),
    placeholderData: keepPreviousData,
    enabled: Boolean(metric),
  });
}

export function useAlerts(q: AlertsQuery) {
  return useQuery({ queryKey: qk.alerts(q), queryFn: () => api.alerts(q), placeholderData: keepPreviousData });
}

export function useBriefing(id: string, asOf: string | null, lang: Lang = "tr") {
  return useQuery({
    queryKey: qk.briefing(id, asOf, lang),
    queryFn: () => api.briefing(id, { as_of: asOf, lang }),
    staleTime: 5 * 60_000,
  });
}

export function useCheckins(id: string, asOf: string | null) {
  return useQuery({ queryKey: qk.checkins(id, asOf), queryFn: () => api.checkins(id, { as_of: asOf, days: 14 }) });
}

/** Olayla ilgili tüm görünümleri tazele (feedback/share sonrası). */
function useInvalidateEvents() {
  const qc = useQueryClient();
  return () =>
    Promise.all(["summary", "alerts", "series", "crew", "scores"].map((k) => qc.invalidateQueries({ queryKey: [k] })));
}

export function useExplain() {
  return useMutation({
    mutationFn: ({ eventId, body }: { eventId: string; body?: Partial<ExplainRequest> }) => api.explain(eventId, body),
  });
}

export function useFeedback() {
  const invalidate = useInvalidateEvents();
  return useMutation({
    mutationFn: ({ eventId, body }: { eventId: string; body: FeedbackRequest }) => api.feedback(eventId, body),
    onSuccess: invalidate,
  });
}

export function useShare() {
  const invalidate = useInvalidateEvents();
  return useMutation({
    mutationFn: ({ eventId, share }: { eventId: string; share: boolean }) => api.share(eventId, share),
    onSuccess: invalidate,
  });
}

export function useSubmitCheckin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CheckinRequest) => api.checkin(body),
    onSuccess: () =>
      Promise.all(["checkins", "summary", "crew", "series", "alerts", "scores"].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
  });
}
