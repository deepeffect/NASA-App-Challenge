/**
 * Skor grafikleri (bağımlılıksız SVG):
 *  - ScoreHistoryChart: günlük genel skor, rules.yaml bantları, seçili gün imleci, üzerine gelince ipucu,
 *    tıklayınca o günü seçer.
 *  - Sparkline: sistem kartlarındaki mini skor grafiği.
 * Skorların tamamı API'den gelir; burada hesap yapılmaz. Renkler index.css'teki tema değişkenleridir.
 */
import { useEffect, useRef, useState, type RefObject } from "react";

import type { ScoreHistoryResponse } from "../../api/client";
import { fmtDate, fmtNum } from "../ui/format";
import { STATUS_LABELS } from "../ui/labels";

/** Kapsayıcının genişliğini izler (SVG'yi gerçek piksel boyutunda çizmek için). */
function useWidth<T extends HTMLElement>(fallback: number): [RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setWidth(Math.max(fallback, el.clientWidth));
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [fallback]);
  return [ref, width];
}

/** null değerlerde kesilen çizgi yolu. */
function linePath(values: (number | null | undefined)[], x: (k: number) => number, y: (v: number) => number): string {
  let d = "";
  let pen = false;
  values.forEach((v, k) => {
    if (v == null) {
      pen = false;
      return;
    }
    d += `${pen ? "L" : "M"}${x(k).toFixed(1)},${y(v).toFixed(1)}`;
    pen = true;
  });
  return d;
}

const H = 250;

export function ScoreHistoryChart({
  history,
  selected,
  onSelect,
}: {
  history: ScoreHistoryResponse;
  selected: string | null;
  onSelect: (date: string) => void;
}) {
  const [ref, W] = useWidth<HTMLDivElement>(280);
  const [hover, setHover] = useState<number | null>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const [tipLeft, setTipLeft] = useState(0);

  const { days, bands } = history;
  const n = days.length;
  const wide = W >= 520;
  const m = { t: 14, r: wide ? 92 : 12, b: 28, l: 34 };
  const x = (k: number) => (n <= 1 ? (m.l + W - m.r) / 2 : m.l + ((W - m.l - m.r) * k) / (n - 1));
  const y = (v: number) => m.t + (H - m.t - m.b) * (1 - v / 100);
  const sel = days.findIndex((d) => d.date === selected);

  // İpucu kutusu grafiğin dışına taşmasın
  useEffect(() => {
    if (hover === null || !tipRef.current) return;
    const tw = tipRef.current.offsetWidth;
    const px = x(hover);
    setTipLeft(Math.min(W - tw - 4, Math.max(4, px + 12 + tw > W ? px - tw - 12 : px + 12)));
    // x, W ve n'e bağlıdır; hover/W değişince yeniden hesaplanır
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hover, W, n]);

  if (!n) return <p className="text-slate-400">Bu aralıkta skor yok.</p>;

  const indexAt = (clientX: number, el: SVGSVGElement) => {
    const r = el.getBoundingClientRect();
    if (n <= 1) return 0;
    return Math.max(0, Math.min(n - 1, Math.round(((clientX - r.left - m.l) / (W - m.l - m.r)) * (n - 1))));
  };

  const scores = days.map((d) => d.score);
  const last = days[n - 1];
  const tickEvery = Math.max(1, Math.ceil(n / 7));
  const marks = [sel, hover].filter((k, i, a): k is number => k != null && k >= 0 && a.indexOf(k) === i);
  const hov = hover != null ? days[hover] : null;

  return (
    <div ref={ref} className="relative w-full">
      <svg
        width={W}
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`Görev günü ${days[0].mission_day}–${last.mission_day} arası günlük sağlık skoru. Son gün: ${fmtNum(last.score, 0)}, ${STATUS_LABELS[last.status]}.`}
        className="block w-full cursor-crosshair touch-pan-y"
        onPointerMove={(e) => setHover(indexAt(e.clientX, e.currentTarget))}
        onPointerLeave={() => setHover(null)}
        onClick={(e) => onSelect(days[indexAt(e.clientX, e.currentTarget)].date)}
      >
        {[0, 20, 40, 60, 80, 100].map((t) => (
          <g key={t}>
            <line x1={m.l} x2={W - m.r} y1={y(t)} y2={y(t)} stroke="var(--chart-grid)" />
            <text x={m.l - 6} y={y(t) + 4} textAnchor="end" fontSize={11} fill="var(--chart-axis)">
              {t}
            </text>
          </g>
        ))}
        {(
          [
            [bands.green_min, `normal: ${fmtNum(bands.green_min, 0)} ve üzeri`],
            [bands.yellow_min, `kritik: ${fmtNum(bands.yellow_min, 0)} altı`],
          ] as const
        ).map(([t, label]) => (
          <g key={label}>
            <line x1={m.l} x2={W - m.r} y1={y(t)} y2={y(t)} stroke="var(--chart-axis)" strokeDasharray="4 4" />
            <text x={m.l + 6} y={y(t) - 5} fontSize={11} fill="var(--chart-axis)">
              {label}
            </text>
          </g>
        ))}
        {days.map((d, k) =>
          k % tickEvery === 0 ? (
            <text key={d.date} x={x(k)} y={H - 8} textAnchor="middle" fontSize={11} fill="var(--chart-axis)">
              {d.mission_day}
            </text>
          ) : null,
        )}
        {wide && (
          <text x={W - m.r + 10} y={H - 8} fontSize={11} fill="var(--chart-axis)">
            görev günü
          </text>
        )}

        {sel >= 0 && <line x1={x(sel)} x2={x(sel)} y1={m.t} y2={H - m.b} stroke="var(--color-slate-300)" strokeWidth={1} />}
        {hover != null && hover !== sel && (
          <line x1={x(hover)} x2={x(hover)} y1={m.t} y2={H - m.b} stroke="var(--chart-axis)" strokeDasharray="2 3" />
        )}

        <path d={linePath(scores, x, y)} fill="none" stroke="var(--series)" strokeWidth={2.5} strokeLinejoin="round" />
        {marks.map((k) =>
          days[k].score != null ? (
            <circle key={k} cx={x(k)} cy={y(days[k].score!)} r={5} fill="var(--series)" stroke="var(--color-slate-900)" strokeWidth={2} />
          ) : null,
        )}

        {wide && last.score != null && (
          <text x={W - m.r + 10} y={y(last.score) + 4} fontSize={12} fontWeight={600} fill="var(--color-slate-100)">
            Skor {fmtNum(last.score, 0)}
          </text>
        )}
      </svg>

      {hov && (
        <div
          ref={tipRef}
          className="pointer-events-none absolute top-1.5 whitespace-nowrap rounded-md bg-slate-100 px-2.5 py-1.5 text-xs leading-snug text-slate-900"
          style={{ left: tipLeft }}
        >
          Görev günü {hov.mission_day} · {fmtDate(hov.date)}
          <br />
          Skor <b>{fmtNum(hov.score, 0)}</b> · {STATUS_LABELS[hov.status]}
          <br />
          seçmek için tıkla
        </div>
      )}
    </div>
  );
}

export function Sparkline({
  values,
  selectedIndex,
  label,
}: {
  values: (number | null | undefined)[];
  selectedIndex: number;
  label: string;
}) {
  const [ref, W] = useWidth<HTMLDivElement>(120);
  const Hs = 40;
  const n = values.length;
  const x = (k: number) => (n <= 1 ? W / 2 : 4 + ((W - 8) * k) / (n - 1));
  const y = (v: number) => 4 + (Hs - 8) * (1 - v / 100);
  const line = linePath(values, x, y);
  const known = values.map((v, k) => (v == null ? -1 : k)).filter((k) => k >= 0);
  const selValue = selectedIndex >= 0 ? values[selectedIndex] : null;

  return (
    <div ref={ref} className="mt-1 w-full">
      {known.length > 0 && (
        <svg width={W} height={Hs} viewBox={`0 0 ${W} ${Hs}`} role="img" aria-label={label} className="block w-full">
          {known.length === n && n > 1 && (
            <path d={`${line}L${x(n - 1)},${Hs}L${x(0)},${Hs}Z`} fill="var(--series)" opacity={0.1} />
          )}
          <path d={line} fill="none" stroke="var(--series)" strokeWidth={1.5} />
          {selValue != null && (
            <circle cx={x(selectedIndex)} cy={y(selValue)} r={4} fill="var(--series)" stroke="var(--color-slate-900)" strokeWidth={2} />
          )}
        </svg>
      )}
    </div>
  );
}
