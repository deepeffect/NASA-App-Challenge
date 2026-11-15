/**
 * "Tüm öz bakım çözümleri" penceresi (üst bardaki i düğmesi açar). Prototip: <dialog id="info">.
 * İçerik katalogdan gelir (`PersonalCatalog.solutions`, GET /api/catalog); iki izleyici için de aynıdır.
 *
 * Yerel <dialog> kullanılır: odak içeride kalır, Esc kapatır, arka plana tıklamak kapatır.
 */
import { type MouseEvent, useEffect, useId, useRef } from "react";

import { useHealthTexts } from "./texts";
import type { Audience, CatalogSolution } from "./types";

export interface SelfCareDialogProps {
  audience: Audience;
  open: boolean;
  onClose: () => void;
  solutions: readonly CatalogSolution[];
}

export function SelfCareDialog({ audience, open, onClose, solutions }: SelfCareDialogProps) {
  const t = useHealthTexts();
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    else if (!open && dialog.open) dialog.close();
  }, [open]);

  // Bütün kapanış yolları (×, arka plan, Esc) pencereyi yerel olarak kapatır; `onClose` sadece yerel `close`
  // olayından ve her kapanışta TEK kez çağrılır.
  // Sadece pencerenin DIŞINA (arka plana) tıklanınca kapat; iç boşluğa tıklamak kapatmaz.
  const onBackdropClick = (e: MouseEvent<HTMLDialogElement>) => {
    if (e.target !== e.currentTarget) return;
    const r = e.currentTarget.getBoundingClientRect();
    const inside = e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
    if (!inside) e.currentTarget.close();
  };

  return (
    <dialog ref={ref} aria-labelledby={titleId} data-audience={audience} onClose={() => onClose()} onClick={onBackdropClick}>
      <div className="dlg-head">
        <h2 id={titleId}>{t.allSolutions}</h2>
        <button type="button" aria-label={t.close} onClick={() => ref.current?.close()}>
          ×
        </button>
      </div>
      <div>
        {solutions.map((sol) => (
          <details key={sol.code} className="sol" data-code={sol.code}>
            <summary>{sol.title}</summary>
            <p className="muted">
              {t.when} {sol.when}
            </p>
            <ol>
              {sol.steps.map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ol>
            <p className="muted">
              {t.contactGroundIf} {sol.contact_ground_if}
            </p>
          </details>
        ))}
      </div>
    </dialog>
  );
}
