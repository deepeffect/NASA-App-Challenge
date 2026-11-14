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

const THRESHOLD_COLORS = { warning: "#fb923c", critical: "#f87171" };

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
  const { domain, visibleThresholds, hiddenThresholds } = useMemo(() => {
    const vals: number[] = [];
    for (const r of rows) {
      if (r.value != null) vals.push(r.value);
      if (r.forecast != null) vals.push(r.forecast);
      if (r.range) vals.push(...r.range);
    }
    if (baseline) vals.push(baseline.mean - baseline.std, baseline.mean + baseline.std);
    if (!vals.length) return { domain: [0, 1] as [number, number], visibleThresholds: thresholds, hiddenThresholds: [] };
    let lo = Math.min(...vals);
    let hi = Math.max(...vals);
    const span = Math.max(hi - lo, Math.abs(hi) * 0.05, 1e-6);
    const visible = thresholds.filter((t) => t.y >= lo - span * 0.6 && t.y <= hi + span * 0.6);
    const hidden = thresholds.filter((t) => !visible.includes(t));
    for (const t of visible) {
      lo = Math.min(lo, t.y);
      hi = Math.max(hi, t.y);
    }
    const pad = (hi - lo) * 0.08 || 1;
    return { domain: [lo - pad, hi + pad] as [number, number], visibleThresholds: visible, hiddenThresholds: hidden };
  }, [rows, baseline, thresholds]);

  if (!rows.length) {
    return <p className="text-slate-400">Bu aralıkta veri yok.</p>;
  }

  const first = dates[0];
  const lastDate = dates[dates.length - 1];
  const inRange = (d: string) => d >= first && d <= lastDate;
  const clamp = (d: string) => (d < first ? first : d > lastDate ? lastDate : d);
  const windowEvents = events.filter((e) => e.window.end >= first && e.window.start <= lastDate);
  const changepoints = events.filter((e): e is HealthEvent & { changepoint_date: string } =>
    Boolean(e.changepoint_date && inRange(e.changepoint_date) && dates.includes(e.changepoint_date)),
  );
  const verifiedNote = metric.threshold_verified ? "" : " (doğrulanmamış)";

  return (
    <figure className="space-y-3">
      <div style={{ height }} aria-label={`${metric.display_name} grafiği`} role="img">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 12, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
            <XAxis dataKey="date" tickFormatter={fmtDateShort} stroke="#94a3b8" tick={{ fontSize: 14 }} minTickGap={24} />
            <YAxis
              domain={domain}
              stroke="#94a3b8"
              tick={{ fontSize: 14 }}
              width={56}
              tickFormatter={(v: number) => fmtNum(v, decimals)}
            />
            <Tooltip
              contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 12, fontSize: 15 }}
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
                fill="#38bdf8"
                fillOpacity={0.1}
                stroke="none"
                ifOverflow="hidden"
              />
            )}

            {windowEvents.map((e) => (
              <ReferenceArea
                key={`w-${e.event_id}`}
                x1={clamp(e.window.start)}
                x2={clamp(e.window.end)}
                fill={SEVERITY_COLORS[e.severity]}
                fillOpacity={0.12}
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
                stroke="#c4b5fd"
                strokeDasharray="4 4"
                label={{ value: "Değişim noktası", position: "insideTopRight", fill: "#c4b5fd", fontSize: 13 }}
              />
            ))}

            {forecastEvents.length > 0 && (
              <Area dataKey="range" stroke="none" fill="#a78bfa" fillOpacity={0.15} isAnimationActive={false} connectNulls={false} />
            )}
            <Line dataKey="roll7" stroke="#64748b" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
            <Line dataKey="value" stroke="#e2e8f0" strokeWidth={2.5} dot={{ r: 2 }} isAnimationActive={false} connectNulls={false} />
            {forecastEvents.length > 0 && (
              <Line dataKey="forecast" stroke="#a78bfa" strokeWidth={2.5} strokeDasharray="6 5" dot={false} isAnimationActive={false} />
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
        {windowEvents.length > 0 && (
          <span><span className="mr-1 inline-block h-3 w-5 bg-orange-400/20 align-middle" />Olay penceresi</span>
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
