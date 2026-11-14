/**
 * Ölçümler tablosu: alan skorları (0–100) + alanlara göre gruplanmış ölçümler. Prototip: <table id="readings">.
 *
 * Değer, sağlıklı aralık ve bayrak metinleri backend'den gelir; burada seviye HESAPLANMAZ. Aralık dışı
 * değerler ikon + metinle işaretlenir ("Aralık dışında" / "Çok dışında"), sadece renkle değil.
 *
 * Dünya görünümü (`audience="earth"`): astronotun paylaşmadığı ruh hali / stres ölçümleri ve davranışsal alan
 * skoru `hidden` gelir; değer yerine "Paylaşılmadı" yazılır, bayrak gösterilmez.
 */
import { Fragment } from "react";

import { checkAudience } from "./audience";
import { Glyph } from "./Glyph";
import { useHealthTexts } from "./texts";
import type { Audience, CatalogDomain, DayView, ReadingView } from "./types";

export interface ReadingsTableProps {
  audience: Audience;
  view: DayView;
  /** Grup sırası ve adları (`PersonalCatalog.domains`). */
  domains: readonly CatalogDomain[];
}

interface Group {
  id: string;
  label: string;
  rows: ReadingView[];
}

/** Ölçümleri katalogdaki alan sırasıyla gruplar; katalogda olmayan alan (olmamalı) sona eklenir. */
function groupReadings(readings: readonly ReadingView[], domains: readonly CatalogDomain[]): Group[] {
  const groups: Group[] = domains.map((d) => ({ id: d.id, label: d.label, rows: [] }));
  for (const r of readings) {
    let g = groups.find((x) => x.id === r.domain);
    if (!g) {
      g = { id: r.domain, label: r.domain, rows: [] };
      groups.push(g);
    }
    g.rows.push(r);
  }
  return groups.filter((g) => g.rows.length > 0);
}

export function ReadingsTable({ audience, view, domains }: ReadingsTableProps) {
  const t = useHealthTexts();
  checkAudience("ReadingsTable", audience, view);

  return (
    <div data-audience={audience}>
      <h2>{t.readings}</h2>
      <div className="scroll">
        <table className="readings">
          <thead>
            <tr>
              <th scope="col">{t.thReading}</th>
              <th scope="col" className="r">
                {t.thValue}
              </th>
              <th scope="col">{t.thHealthy}</th>
              <th scope="col">
                <span className="vh">{t.thFlag}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr className="grp">
              <td colSpan={4}>{t.areaScores}</td>
            </tr>
            {view.areas.map((a) => (
              <tr key={a.area} data-hidden={a.hidden ? "true" : undefined}>
                <td className="name">{a.label}</td>
                <td className="r num">{a.hidden ? t.notShared : a.score_text}</td>
                <td />
                <td className="flag">{a.main_concern ? t.mainConcern : ""}</td>
              </tr>
            ))}
            {groupReadings(view.readings, domains).map((g) => (
              <Fragment key={g.id}>
                <tr className="grp">
                  <td colSpan={4}>{g.label}</td>
                </tr>
                {g.rows.map((r) => (
                  <tr key={r.col} data-col={r.col} data-hidden={r.hidden ? "true" : undefined}>
                    <td className="name">
                      {r.label} <span className="unit">{r.unit}</span>
                    </td>
                    <td className="r num">{r.hidden ? t.notShared : r.value_text}</td>
                    <td className="num">{r.healthy_text}</td>
                    <td className="flag">
                      {!r.hidden && (r.level === 1 || r.level === 2) ? (
                        <>
                          <Glyph level={r.level} small /> {r.flag_text}
                        </>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted" style={{ marginTop: 8 }}>
        {view.readings_note}
      </p>
      <p className="muted">{view.threshold_note}</p>
    </div>
  );
}
