/**
 * Sağlık skoru grafiği: kümülatif skor (kalın çizgi) + tek günlük skor (ince çizgi), 80 ve 65 eşik çizgileri,
 * seçili gün işareti, fareyle ipucu, tıklayınca gün seçimi. Prototip: drawChart().
 *
 * Skorlar backend'den gelir; burada hesaplanmaz. Sayı biçimi prototiple aynıdır (toFixed, bir ondalık).
 */
import { type MouseEvent, type PointerEvent, useLayoutEffect, useRef, useState } from "react";

import { formatNumber, useHealthTexts } from "./texts";
import type { Audience, ScorePoint } from "./types";

/**
 * Prototipin grafiğindeki iki yatay çizgi: "normal from 80" ve "unwell below 65". Sadece görsel
 * referanstır; durum bu sayılardan HESAPLANMAZ, veri setinden okunur. Sayılar simüle veri setinin skor
 * ölçeğinden gelir, tıbbi doğrulaması yoktur (threshold_source: dataset, verified: false — CLAUDE.md, kural 3).
 */
export const SCORE_NORMAL_FROM = 80;
export const SCORE_UNWELL_BELOW = 65;

const HEIGHT = 210;
const MARGIN = { t: 12, r: 10, b: 26, l: 30 };

export interface ScoreChartProps {
  audience: Audience;
  /** Gün başına skor: `PersonalOverview.strip` doğrudan verilir (kümülatif `score` + tek günlük `daily_score`). */
  points: readonly ScorePoint[];
  /** Seçili gün, 1'den başlar. */
  selectedDay: number;
  /** Grafiğe tıklanınca en yakın gün seçilir. */
  onSelectDay?: (day: number) => void;
}

export function ScoreChart({ audience, points, selectedDay, onSelectDay }: ScoreChartProps) {
  const t = useHealthTexts();
  const wrapRef = useRef<HTMLDivElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [tipLeft, setTipLeft] = useState(4);

  // Genişlik kaptan ölçülür (kapalı <details> içinde 0'dır; açılınca gözlemci yeniden ölçer).
  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => setWidth(el.clientWidth);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const n = points.length;
  const hasDaily = n > 0 && points.every((p) => typeof p.daily_score === "number");
  const selected = points.findIndex((p) => p.day === selectedDay);
  const hover = hoverIndex !== null && hoverIndex < n ? hoverIndex : null;

  // Alt sınır prototipteki gibi: en düşük skor 10'a aşağı yuvarlanır, en fazla 20.
  const lowest = Math.min(...points.flatMap((p) => (typeof p.daily_score === "number" ? [p.score, p.daily_score] : [p.score])));
  const y0 = n > 0 ? Math.max(0, Math.min(20, Math.floor(lowest / 10) * 10)) : 20;
  const plotWidth = Math.max(0, width - MARGIN.l - MARGIN.r);
  const plotHeight = HEIGHT - MARGIN.t - MARGIN.b;
  const x = (k: number) => MARGIN.l + (n > 1 ? (plotWidth * k) / (n - 1) : plotWidth / 2);
  const y = (v: number) => MARGIN.t + plotHeight * (1 - (v - y0) / (100 - y0));
  const path = (values: number[]) => values.map((v, k) => `${k ? "L" : "M"}${x(k).toFixed(1)},${y(v).toFixed(1)}`).join("");

  const hoverX = hover !== null ? x(hover) : 0;
  useLayoutEffect(() => {
    if (hover === null || !tipRef.current) return;
    const tipWidth = tipRef.current.offsetWidth;
    const right = hoverX + 12;
    setTipLeft(Math.min(width - tipWidth - 4, Math.max(4, right + tipWidth > width ? hoverX - tipWidth - 12 : right)));
  }, [hover, hoverX, width, t]);

  const indexAt = (e: MouseEvent<SVGSVGElement>) => {
    const left = e.currentTarget.getBoundingClientRect().left;
    const k = plotWidth > 0 ? Math.round(((e.clientX - left - MARGIN.l) / plotWidth) * (n - 1)) : 0;
    return Math.max(0, Math.min(n - 1, k));
  };
  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const k = indexAt(e);
    if (k !== hoverIndex) setHoverIndex(k);
  };

  const gridValues: number[] = [];
  for (let v = y0; v <= 100; v += 20) gridValues.push(v);
  const thresholds: [number, string][] = [
    [SCORE_NORMAL_FROM, t.normalFrom(SCORE_NORMAL_FROM)],
    [SCORE_UNWELL_BELOW, t.unwellBelow(SCORE_UNWELL_BELOW)],
  ];
  const marked = [selected, hover].filter((k, i, all): k is number => k !== null && k >= 0 && all.indexOf(k) === i);
  const hovered = hover !== null ? points[hover] : undefined;

  return (
    <div data-audience={audience}>
      <h2>{t.chartTitle(n)}</h2>
      <div className="legend">
        <span>
          <i className="cum" />
          {t.running}
        </span>
        {hasDaily ? (
          <span>
            <i className="day" />
            {t.singleDay}
          </span>
        ) : null}
      </div>
      <div className="chart" ref={wrapRef}>
        {width > 0 && n > 0 ? (
          <svg
            width={width}
            height={HEIGHT}
            viewBox={`0 0 ${width} ${HEIGHT}`}
            role="img"
            aria-label={hasDaily ? t.chartAria(n) : t.chartAriaRunning(n)}
            onPointerMove={onMove}
            onPointerLeave={() => setHoverIndex(null)}
            onClick={(e) => onSelectDay?.(points[indexAt(e)].day)}
          >
            {gridValues.map((v) => (
              <g key={v}>
                <line x1={MARGIN.l} x2={width - MARGIN.r} y1={y(v)} y2={y(v)} stroke="var(--line)" />
                <text x={MARGIN.l - 6} y={y(v) + 4} textAnchor="end" fontSize="11" fill="var(--muted)">
                  {v}
                </text>
              </g>
            ))}
            {thresholds.map(([v, label]) => (
              <g key={v}>
                <line x1={MARGIN.l} x2={width - MARGIN.r} y1={y(v)} y2={y(v)} stroke="var(--muted)" strokeDasharray="4 4" />
                <text x={MARGIN.l + 6} y={y(v) - 5} fontSize="11" fill="var(--muted)">
                  {label}
                </text>
              </g>
            ))}
            {points.map((p, k) =>
              k % 5 === 0 ? (
                <text key={p.day} x={x(k)} y={HEIGHT - 7} textAnchor="middle" fontSize="11" fill="var(--muted)">
                  {t.chartDay(p.day)}
                </text>
              ) : null,
            )}
            {selected >= 0 ? (
              <line x1={x(selected)} x2={x(selected)} y1={MARGIN.t} y2={HEIGHT - MARGIN.b} stroke="var(--ink-2)" />
            ) : null}
            {hover !== null && hover !== selected ? (
              <line x1={hoverX} x2={hoverX} y1={MARGIN.t} y2={HEIGHT - MARGIN.b} stroke="var(--muted)" strokeDasharray="2 3" />
            ) : null}
            {hasDaily ? (
              <path
                d={path(points.map((p) => p.daily_score as number))}
                fill="none"
                stroke="var(--series-day)"
                strokeWidth="1.5"
                strokeLinejoin="round"
              />
            ) : null}
            <path d={path(points.map((p) => p.score))} fill="none" stroke="var(--series-cum)" strokeWidth="2.5" strokeLinejoin="round" />
            {marked.map((k) => (
              <g key={k}>
                {hasDaily ? (
                  <circle cx={x(k)} cy={y(points[k].daily_score as number)} r="4.5" fill="var(--series-day)" stroke="var(--surface)" strokeWidth="2" />
                ) : null}
                <circle cx={x(k)} cy={y(points[k].score)} r="5" fill="var(--series-cum)" stroke="var(--surface)" strokeWidth="2" />
              </g>
            ))}
          </svg>
        ) : null}
        <div className="tip" ref={tipRef} aria-hidden="true" style={{ display: hovered ? "block" : "none", left: tipLeft }}>
          {hovered ? (
            <>
              {t.tipDay(hovered.day)}
              <br />
              {t.tipRunning} <b>{formatNumber(hovered.score, 1, t)}</b>
              {typeof hovered.daily_score === "number" && hasDaily ? (
                <>
                  {" · "}
                  {t.tipSingle} <b>{formatNumber(hovered.daily_score, 1, t)}</b>
                </>
              ) : null}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
