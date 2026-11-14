/**
 * Metrik grafiği. Katmanlar (veri yoksa çizilmez):
 *  - kişisel normal bandı (baseline ± std)
 *  - eşik çizgileri (doğrulanmamışsa etikette "doğrulanmamış")
 *  - olay pencereleri (window) → gölgeli bölge
 *  - changepoint_date → dikey kesikli çizgi
 *  - forecast → kesikli tahmin çizgisi + belirsizlik bandı
 */
import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { HealthEvent, MetricSeriesResponse } from "../../api/client";
import { fmtDate, fmtDateShort, fmtNum, unitLabel } from "../ui/format";
import { SEVERITY_COLORS } from "../ui/labels";

interface Row {
  date: string;
  value?: number;
  roll7?: number | null;
  forecast?: number;
  range?: [number, number];
}

interface ThresholdLine {
  y: number;
  level: "warning" | "critical";
  side: "low" | "high";
}

const THRESHOLD_COLORS = { warning: "var(--sev-warning)", critical: "var(--sev-critical)" };
const SEV_RANK = { info: 1, warning: 2, critical: 3 } as const;
const RANK_SEV = { 1: "info", 2: "warning", 3: "critical" } as const;

/** Okunur eksen değerleri: 1-2-2,5-5 × 10^n adımlarıyla yuvarlanmış alan ve tikler. */
function niceScale(lo: number, hi: number, count = 5): { domain: [number, number]; ticks: number[] } {
  const raw = Math.max((hi - lo) / count, 1e-9);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
  const a = Math.floor(lo / step) * step;
  const b = Math.ceil(hi / step) * step;
  const ticks: number[] = [];
  for (let v = a; v <= b + step / 2; v += step) ticks.push(Number(v.toFixed(10)));
  return { domain: [a, b], ticks };
}

export function MetricChart({ series, height = 320 }: { series: MetricSeriesResponse; height?: number }) {
  const { metric, baseline, daily, events } = series;
  const decimals = metric.decimals;
  const unit = unitLabel(metric.unit);

  const { rows, dates, forecastEvents } = useMemo(() => {
    const byDate = new Map<string, Row>();
    for (const p of daily) byDate.set(p.date, { date: p.date, value: p.value, roll7: p.roll7 });
    const fc = events.filter((e) => e.forecast && e.forecast.metric === metric.name);
    for (const e of fc) {
      for (const p of e.forecast!.points) {
        const row = byDate.get(p.date) ?? { date: p.date };
        row.forecast = p.value;
        if (p.lower != null && p.upper != null) row.range = [p.lower, p.upper];
        byDate.set(p.date, row);
      }
    }
    // Tahmin çizgisi son gerçek noktadan başlasın
    const last = daily.at(-1);
    if (last && fc.length) {
      const row = byDate.get(last.date)!;
      row.forecast = last.value;
    }
    const sorted = [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
    return { rows: sorted, dates: sorted.map((r) => r.date), forecastEvents: fc };
  }, [daily, events, metric.name]);

  const thresholds = useMemo<ThresholdLine[]>(() => {
    const t = metric.thresholds;
    if (!t) return [];
    const out: ThresholdLine[] = [];
    for (const level of ["warning", "critical"] as const) {
      const r = t[level];
      if (r?.low != null) out.push({ y: r.low, level, side: "low" });
      if (r?.high != null) out.push({ y: r.high, level, side: "high" });
    }
    return out;
  }, [metric.thresholds]);

  // Y ekseni: veri + bant + tahmin; uzak eşikler grafiği ezmesin diye ayrıca listelenir.
  const { domain, ticks, visibleThresholds, hiddenThresholds } = useMemo(() => {
    const vals: number[] = [];
    for (const r of rows) {
      if (r.value != null) vals.push(r.value);
      if (r.forecast != null) vals.push(r.forecast);
      if (r.range) vals.push(...r.range);
    }
    if (baseline) vals.push(baseline.mean - baseline.std, baseline.mean + baseline.std);
    if (!vals.length) return { ...niceScale(0, 1), visibleThresholds: thresholds, hiddenThresholds: [] };
    let lo = Math.min(...vals);
    let hi = Math.max(...vals);
    const span = Math.max(hi - lo, Math.abs(hi) * 0.05, 1e-6);
    const visible = thresholds.filter((t) => t.y >= lo - span * 0.6 && t.y <= hi + span * 0.6);
    const hidden = thresholds.filter((t) => !visible.includes(t));
    for (const t of visible) {
      lo = Math.min(lo, t.y);
      hi = Math.max(hi, t.y);
    }
    const pad = (hi - lo) * 0.05 || 1;
    return { ...niceScale(lo - pad, hi + pad), visibleThresholds: visible, hiddenThresholds: hidden };
  }, [rows, baseline, thresholds]);

  // Olay pencereleri: üst üste binen pencereler opaklığı katlayıp veriyi örtmesin diye gün bazında
  // birleştirilir; her gün, onu kapsayan olayların en yüksek ciddiyetinin rengini alır.
  const windowBands = useMemo(() => {
    const level = new Map<string, number>();
    for (const e of events) {
      if (e.source === "forecast") continue; // tahminin penceresi uydurma aralığıdır, olay dönemi değil
      for (const d of dates) {
        if (d >= e.window.start && d <= e.window.end) level.set(d, Math.max(level.get(d) ?? 0, SEV_RANK[e.severity]));
      }
    }
    const bands: { x1: string; x2: string; severity: keyof typeof SEV_RANK }[] = [];
    let cur: { x1: string; x2: string; l: number } | null = null;
    for (const d of dates) {
      const l = level.get(d) ?? 0;
      if (cur && l === cur.l) {
        cur.x2 = d;
        continue;
      }
      if (cur) bands.push({ x1: cur.x1, x2: cur.x2, severity: RANK_SEV[cur.l as 1 | 2 | 3] });
      cur = l ? { x1: d, x2: d, l } : null;
    }
    if (cur) bands.push({ x1: cur.x1, x2: cur.x2, severity: RANK_SEV[cur.l as 1 | 2 | 3] });
    return bands;
  }, [events, dates]);

  if (!rows.length) {
    return <p className="text-slate-400">Bu aralıkta veri yok.</p>;
  }

  const first = dates[0];
  const lastDate = dates[dates.length - 1];
  const inRange = (d: string) => d >= first && d <= lastDate;
  const changepoints = events.filter((e): e is HealthEvent & { changepoint_date: string } =>
    Boolean(e.changepoint_date && inRange(e.changepoint_date) && dates.includes(e.changepoint_date)),
  );
  const verifiedNote = metric.threshold_verified ? "" : " (doğrulanmamış)";

  return (
    <figure className="space-y-3">
      <div style={{ height }} aria-label={`${metric.display_name} grafiği`} role="img">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 12, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 3" />
            <XAxis dataKey="date" tickFormatter={fmtDateShort} stroke="var(--chart-axis)" tick={{ fontSize: 13 }} minTickGap={24} />
            <YAxis
              domain={domain}
              ticks={ticks}
              stroke="var(--chart-axis)"
              tick={{ fontSize: 13 }}
              width={56}
              tickFormatter={(v: number) => fmtNum(v, decimals)}
            />
            <Tooltip
              contentStyle={{ background: "var(--color-slate-900)", border: "1px solid var(--color-slate-600)", borderRadius: 8, fontSize: 14 }}
              labelStyle={{ color: "var(--color-slate-100)" }}
              itemStyle={{ color: "var(--color-slate-300)" }}
              labelFormatter={(d) => fmtDate(String(d))}
              formatter={(v, name) => {
                const label = name === "value" ? "Değer" : name === "roll7" ? "7 gün ort." : name === "forecast" ? "Tahmin" : "Tahmin aralığı";
                const text = Array.isArray(v)
                  ? `${fmtNum(Number(v[0]), decimals)} – ${fmtNum(Number(v[1]), decimals)} ${unit}`
                  : `${fmtNum(Number(v), decimals)} ${unit}`;
                return [text, label];
              }}
            />

            {baseline && (
              <ReferenceArea
                y1={baseline.mean - baseline.std}
                y2={baseline.mean + baseline.std}
                fill="var(--chart-band)"
                fillOpacity={0.12}
                stroke="none"
                ifOverflow="hidden"
              />
            )}

            {windowBands.map((b) => (
              <ReferenceArea
                key={`w-${b.x1}`}
                x1={b.x1}
                x2={b.x2}
                fill={SEVERITY_COLORS[b.severity]}
                fillOpacity={0.14}
                stroke="none"
                ifOverflow="hidden"
              />
            ))}

            {visibleThresholds.map((t) => (
              <ReferenceLine
                key={`t-${t.level}-${t.side}`}
                y={t.y}
                stroke={THRESHOLD_COLORS[t.level]}
                strokeDasharray="6 4"
                label={{
                  value: `${t.level === "critical" ? "Kritik" : "Uyarı"} eşiği${verifiedNote}`,
                  position: t.side === "low" ? "insideBottomLeft" : "insideTopLeft",
                  fill: THRESHOLD_COLORS[t.level],
                  fontSize: 13,
                }}
              />
            ))}

            {changepoints.map((e) => (
              <ReferenceLine
                key={`cp-${e.event_id}`}
                x={e.changepoint_date}
                stroke="var(--chart-forecast)"
                strokeDasharray="4 4"
                label={{ value: "Değişim noktası", position: "insideTopRight", fill: "var(--chart-forecast)", fontSize: 13 }}
              />
            ))}

            {forecastEvents.length > 0 && (
              <Area dataKey="range" stroke="none" fill="var(--chart-forecast)" fillOpacity={0.15} isAnimationActive={false} connectNulls={false} />
            )}
            <Line dataKey="roll7" stroke="var(--chart-roll)" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
            <Line dataKey="value" stroke="var(--chart-value)" strokeWidth={2.5} dot={{ r: 2 }} isAnimationActive={false} connectNulls={false} />
            {forecastEvents.length > 0 && (
              <Line dataKey="forecast" stroke="var(--chart-forecast)" strokeWidth={2.5} strokeDasharray="6 5" dot={false} isAnimationActive={false} />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <figcaption className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-slate-400">
        <span><span className="mr-1 inline-block h-0.5 w-5 bg-slate-200 align-middle" />Günlük değer</span>
        <span><span className="mr-1 inline-block h-0.5 w-5 bg-slate-500 align-middle" />7 gün ortalaması</span>
        {baseline && (
          <span>
            <span className="mr-1 inline-block h-3 w-5 bg-sky-400/20 align-middle" />
            Kişisel normal ({fmtNum(baseline.mean, decimals)} ± {fmtNum(baseline.std, decimals)} {unit})
          </span>
        )}
        {visibleThresholds.length > 0 && (
          <span><span className="mr-1 inline-block w-5 border-t-2 border-dashed border-orange-400 align-middle" />Eşik{verifiedNote}</span>
        )}
        {windowBands.length > 0 && (
          <span>
            <span className="mr-1 inline-block h-3 w-5 bg-orange-400/25 align-middle" />
            Olay dönemi (turuncu: uyarı, kırmızı: kritik)
          </span>
        )}
        {changepoints.length > 0 && (
          <span><span className="mr-1 inline-block h-3 w-0 border-l-2 border-dashed border-violet-300 align-middle" />Değişim noktası</span>
        )}
        {forecastEvents.length > 0 && (
          <span><span className="mr-1 inline-block w-5 border-t-2 border-dashed border-violet-400 align-middle" />Tahmin</span>
        )}
      </figcaption>
      {hiddenThresholds.length > 0 && (
        <p className="text-sm text-slate-500">
          Grafik aralığı dışındaki eşikler:{" "}
          {hiddenThresholds
            .map((t) => `${t.level === "critical" ? "kritik" : "uyarı"} ${t.side === "low" ? "alt" : "üst"} ${fmtNum(t.y, decimals)} ${unit}`)
            .join(" · ")}
          {verifiedNote}
        </p>
      )}
    </figure>
  );
}
