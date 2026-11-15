/**
 * Durum kartı: başlık (durum + alt başlık), sağlık skoru, 30 günlük çubuk şeridi, gün seçimi ve
 * önceki/sonraki düğmeleri. Prototip: <section class="card status">.
 *
 * Hiçbir şey hesaplanmaz: durum, skor ve etiketler backend'den gelir (`StripDay`, `DayView`). Çubuk yüksekliği
 * kümülatif skordur; renk sadece durum 1/2 iken vardır ve başlıkta ikon + metinle birlikte verilir.
 */
import { type CSSProperties, useEffect, useLayoutEffect, useRef, useState } from "react";

import { checkAudience } from "./audience";
import { Glyph } from "./Glyph";
import { useHealthTexts } from "./texts";
import type { Audience, DayView, StripDay } from "./types";

export interface StatusCardProps {
  audience: Audience;
  /** Şerit: her gün bir çubuk (`PersonalOverview.strip`). */
  strip: StripDay[];
  /** Seçili gün, 1'den başlar. */
  selectedDay: number;
  onSelectDay: (day: number) => void;
  /** Seçili günün görünümü. Yüklenirken verilmeyebilir; o zaman başlık şeritteki bilgiyle dolar. */
  view?: DayView | null;
  /** Açıklama satırındaki durum adları (`PersonalCatalog.statuses`); verilmezse yerleşik metinler. */
  statusLabels?: readonly string[];
}

const NBSP = " ";

export function StatusCard({ audience, strip, selectedDay, onSelectDay, view, statusLabels }: StatusCardProps) {
  const t = useHealthTexts();
  checkAudience("StatusCard", audience, view);

  const n = strip.length;
  const current = strip.find((d) => d.day === selectedDay);
  const dayView = view && view.day === selectedDay ? view : null;
  const status = dayView?.status ?? current?.status ?? 0;
  const labels = statusLabels && statusLabels.length >= 3 ? statusLabels : t.statuses;

  // Prototipteki gibi çubuklar ilk çizimde 0'dan yükselir (CSS geçişi; hareket azaltma açıksa anında).
  const [grown, setGrown] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setGrown(true));
    return () => cancelAnimationFrame(id);
  }, []);

  // Çubuk ipucu: fareyle üzerine gelince veya KLAVYEYLE odaklanınca; şeridin dışına taşmaz.
  const stripRef = useRef<HTMLDivElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<{ day: number; center: number } | null>(null);
  const [tipLeft, setTipLeft] = useState(0);
  const tipDay = tip ? strip.find((d) => d.day === tip.day) : undefined;
  // Skoru olmayan veri setinde ipucu backend etiketidir ("Gün 5: Dikkat"); çubuklar eşit boydadır.
  const tipText = tipDay ? (tipDay.score_text ? t.stripTip(tipDay.day, tipDay.score_text, tipDay.status_label) : tipDay.label) : "";
  const hasScores = strip.some((d) => d.score !== null);
  const scoreText = dayView?.score_text ?? current?.score_text ?? NBSP;
  useLayoutEffect(() => {
    if (!tip || !stripRef.current || !tipRef.current) return;
    const width = stripRef.current.clientWidth;
    const tipWidth = tipRef.current.offsetWidth;
    setTipLeft(Math.max(0, Math.min(width - tipWidth, tip.center - tipWidth / 2)));
  }, [tip, tipText]);
  const showTip = (day: number, el: HTMLElement) => setTip({ day, center: el.offsetLeft + el.offsetWidth / 2 });

  const go = (day: number) => {
    const next = Math.max(1, Math.min(n, day));
    if (next !== selectedDay) onSelectDay(next);
  };
  const days = { "--days": n } as CSSProperties;

  return (
    <section className="card status" data-audience={audience}>
      {/* Gün değişince ekran okuyucuya tek ve tam bir cümle: hangi gün, durum, alt başlık, skor. */}
      <p className="vh" aria-live="polite" aria-atomic="true">
        {dayView
          ? `${dayView.day_label}. ${dayView.status_label}. ${dayView.subtitle}.${dayView.score_text ? ` ${t.healthScore} ${dayView.score_text}` : ""}`
          : ""}
      </p>
      <div className="headline">
        <div>
          <div className="state">
            <Glyph level={status} />
            {dayView?.status_label ?? current?.status_label ?? NBSP}
          </div>
          <div className="state-sub">{dayView?.subtitle ?? NBSP}</div>
        </div>
        {scoreText ? (
          <div className="score">
            <b className="num">{scoreText}</b>
            <span className="muted">{t.healthScore}</span>
          </div>
        ) : null}
      </div>
      <div>
        <div className="stripwrap">
          <div
            className="strip"
            ref={stripRef}
            role="group"
            aria-label={t.stripLabel(n)}
            style={days}
            onPointerLeave={() => setTip(null)}
          >
            {strip.map((d) => (
              <button
                key={d.day}
                type="button"
                className={`s${d.status}`}
                aria-label={d.label}
                aria-current={d.day === selectedDay ? "true" : undefined}
                onClick={() => go(d.day)}
                onPointerEnter={(e) => showTip(d.day, e.currentTarget)}
                onFocus={(e) => {
                  // Sadece klavye odağında: dokunma/fare tıklamasının verdiği odak ipucunu ekranda bırakmasın.
                  if (e.currentTarget.matches(":focus-visible")) showTip(d.day, e.currentTarget);
                }}
                onBlur={() => setTip(null)}
              >
                <span style={{ height: grown ? `${d.score === null ? 100 : Math.max(4, Math.min(100, d.score))}%` : 0 }} />
              </button>
            ))}
          </div>
          <div className="stip" ref={tipRef} aria-hidden="true" style={{ display: tip ? "block" : "none", left: tipLeft }}>
            {tipText}
          </div>
        </div>
        <div className="ticks num" aria-hidden="true" style={days}>
          {strip.map((d, k) =>
            d.day === selectedDay ? (
              <span key={d.day} className="sel">
                {d.day}
              </span>
            ) : (
              <span key={d.day}>{(k === 0 || (k + 1) % 10 === 0) && Math.abs(d.day - selectedDay) > 1 ? d.day : ""}</span>
            ),
          )}
        </div>
        <div className="dayrow" style={{ marginTop: 4 }}>
          <button type="button" aria-label={t.prevDay} onClick={() => go(selectedDay - 1)}>
            ‹
          </button>
          <span className="num">{dayView?.day_label ?? NBSP}</span>
          <button type="button" aria-label={t.nextDay} onClick={() => go(selectedDay + 1)}>
            ›
          </button>
        </div>
        <div className="key muted" style={{ marginTop: 10 }}>
          {hasScores ? <span>{t.barHeight}</span> : null}
          {labels.slice(0, 3).map((label, level) => (
            <span key={level}>
              <i className={`k${level}`} />
              {label}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
