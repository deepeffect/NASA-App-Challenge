/**
 * 30 günlük kümülatif sağlık skoru (StripDay.score). Üstte tek seri çizgi (kendi aralığına ölçekli,
 * en az 20 puanlık pencere: küçük oynamalar abartılmasın), altında gün şeridi: her gün için durum
 * şekli (boş = normal, üçgen = dikkat, karo = rahatsız). Bugünün noktası vurgulu.
 * Üzerine gelince / klavyeyle odaklanınca o günün backend etiketi ("Gün 3: Dikkat, skor 74") görünür.
 */
import { useEffect, useRef, useState } from "react";

import type { StripDay } from "../../api/station";
import { useT } from "./texts";

const LINE_H = 50;
const ROW_H = 12;
const H = LINE_H + ROW_H + 4;
const PAD = { t: 6, r: 6, l: 6 };
const MIN_SPAN = 20;

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(el.clientWidth));
    ro.observe(el);
    setW(el.clientWidth);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

function domain(scores: number[]): [number, number] {
  let lo = Math.floor((Math.min(...scores) - 3) / 5) * 5;
  let hi = Math.ceil((Math.max(...scores) + 3) / 5) * 5;
  if (hi - lo < MIN_SPAN) {
    const mid = (hi + lo) / 2;
    lo = mid - MIN_SPAN / 2;
    hi = mid + MIN_SPAN / 2;
  }
  if (hi > 100) [lo, hi] = [lo - (hi - 100), 100];
  if (lo < 0) [lo, hi] = [0, hi - lo];
  return [lo, hi];
}

export function Sparkline({ strip }: { strip: StripDay[] }) {
  const { t } = useT();
  const [ref, W] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const n = strip.length;
  if (!n) return null;
  const scores = strip.map((d) => d.score);
  const [lo, hi] = domain(scores);
  const x = (k: number) => PAD.l + ((W - PAD.l - PAD.r) * k) / Math.max(1, n - 1);
  const y = (v: number) => PAD.t + (LINE_H - PAD.t - 4) * (1 - (v - lo) / (hi - lo));
  const rowY = LINE_H + 4 + ROW_H / 2;
  const path = scores.map((v, k) => `${k ? "L" : "M"}${x(k).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const last = strip[n - 1];
  const minDay = strip.reduce((m, d) => (d.score < m.score ? d : m), strip[0]);
  const label = t("sparkLabel", { first: strip[0].score_text, last: last.score_text, min: minDay.score_text });

  const pick = (clientX: number) => {
    const el = ref.current;
    if (!el || n < 2) return;
    const r = el.getBoundingClientRect();
    setHover(Math.max(0, Math.min(n - 1, Math.round(((clientX - r.left - PAD.l) / (W - PAD.l - PAD.r)) * (n - 1)))));
  };

  return (
    <div className="spark" ref={ref}>
      {W > 0 && (
        <svg
          viewBox={`0 0 ${W} ${H}`}
          height={H}
          role="img"
          aria-label={label}
          tabIndex={0}
          onPointerMove={(e) => pick(e.clientX)}
          onPointerLeave={() => setHover(null)}
          onFocus={() => setHover(n - 1)}
          onBlur={() => setHover(null)}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") setHover((h) => Math.max(0, (h ?? n - 1) - 1));
            if (e.key === "ArrowRight") setHover((h) => Math.min(n - 1, (h ?? n - 1) + 1));
          }}
        >
          <line x1={PAD.l} x2={W - PAD.r} y1={LINE_H} y2={LINE_H} stroke="var(--line)" />
          {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={H} stroke="var(--muted)" />}
          <path d={path} fill="none" stroke="var(--series-cum)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {strip.map((d, k) => {
            const cx = x(k);
            if (d.status === 2)
              return <rect key={k} x={cx - 3} y={rowY - 3} width={6} height={6} fill="var(--crit)" transform={`rotate(45 ${cx} ${rowY})`} />;
            if (d.status === 1) return <path key={k} d={`M${cx},${rowY - 4.2}L${cx + 4},${rowY + 3}L${cx - 4},${rowY + 3}Z`} fill="var(--warn)" />;
            return <line key={k} x1={cx - 2} x2={cx + 2} y1={rowY} y2={rowY} stroke="var(--quiet)" strokeWidth={2} strokeLinecap="round" />;
          })}
          <circle cx={x(n - 1)} cy={y(last.score)} r={4.5} fill="var(--series-cum)" stroke="var(--surface)" strokeWidth={2} />
          {hover !== null && hover !== n - 1 && <circle cx={x(hover)} cy={y(strip[hover].score)} r={4} fill="var(--ink)" stroke="var(--surface)" strokeWidth={2} />}
        </svg>
      )}
      {hover !== null && W > 0 && (
        <div className="tip" style={{ left: Math.max(80, Math.min(W - 80, x(hover))) }} aria-hidden="true">
          {strip[hover].label}
        </div>
      )}
      <div className="ax" aria-hidden="true">
        <span>{t("sparkStart")}</span>
        <span>{t("sparkToday")}</span>
      </div>
    </div>
  );
}
