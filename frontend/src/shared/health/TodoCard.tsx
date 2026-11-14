/**
 * To-do kartı: sadece yapılması gerekenler. Prototip: <section class="card todo">.
 *
 * Başlık, "yapılacak bir şey yok" metni, yer desteği uyarısı, öğelerin gerekçesi ve maskeli öğe notu
 * backend'den hazır gelir (izleyiciye göre): astronotta "Yapılacaklar", Dünya'da "Astronota gösterilen öneriler".
 *
 * `audience` şunları belirler:
 *   - astronaut: bugünün öğelerinde "Yaptım" düğmesi (`onToggleDone` verildiyse).
 *   - earth: düğme yok (salt okunur); tetikleyicisi sadece gizli ölçümler olan öğeler listede yoktur,
 *     sadece sayıları yazılır (`todo_masked_count`).
 */
import { checkAudience } from "./audience";
import { useHealthTexts } from "./texts";
import type { Audience, DayView } from "./types";

export interface TodoCardProps {
  audience: Audience;
  view: DayView;
  /** "Yaptım" / geri al. Sadece astronot ve sadece bugün için gösterilir (`POST /api/actions/done`). */
  onToggleDone?: (code: string, done: boolean) => void;
  /** Kaydı süren öğenin kodu: düğmesi geçici olarak tıklanamaz (aria-disabled; odak düğmede kalır). */
  busyCode?: string | null;
}

export function TodoCard({ audience, view, onToggleDone, busyCode }: TodoCardProps) {
  const t = useHealthTexts();
  checkAudience("TodoCard", audience, view);

  const canMark = audience === "astronaut" && view.is_today && onToggleDone !== undefined;
  const masked = audience === "earth" ? view.todo_masked_count : 0;

  return (
    <section className="card todo" data-audience={audience}>
      <h2>{view.todo_title}</h2>
      {view.calm_text ? <p className="calm">{view.calm_text}</p> : null}
      {view.ground ? (
        <p className="ground">
          <b>{view.ground_title}</b> {view.ground_text}
        </p>
      ) : null}
      {view.todo.length > 0 ? (
        // key: gün (veya astronot) değişince liste yeniden kurulur ve açık adımlar kapanır (prototipteki gibi);
        // "Yaptım" işaretinde veya aynı günün yenilenmesinde açık kalır.
        <ul className="items" key={`${view.astronaut_id}:${view.day}`}>
          {view.todo.map((item) => (
            <li key={item.code} className="item" data-code={item.code} data-done={item.done ? "true" : undefined}>
              <details>
                <summary>
                  <b>{item.title}</b>
                  <span className="muted">{item.why}</span>
                  <span className="tgl" aria-hidden="true">
                    <span className="tgl-show">{t.steps}</span>
                    <span className="tgl-hide">{t.hide}</span>
                  </span>
                </summary>
                <ol>
                  {item.steps.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ol>
                <p className="muted">
                  {t.contactGroundIf} {item.contact_ground_if}
                </p>
              </details>
              {canMark ? (
                <div className="itemact">
                  <button
                    type="button"
                    className="donebtn"
                    aria-pressed={item.done}
                    aria-disabled={busyCode === item.code || undefined}
                    onClick={() => {
                      if (busyCode !== item.code) onToggleDone(item.code, !item.done);
                    }}
                  >
                    {item.done ? <span aria-hidden="true">✓ </span> : null}
                    {t.didIt}
                  </button>
                </div>
              ) : item.done ? (
                <div className="itemact">
                  <span className="donemark">
                    <span aria-hidden="true">✓ </span>
                    {t.doneMark[audience]}
                  </span>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {masked > 0 && view.todo_masked_text ? (
        <p className="muted" style={{ marginTop: 8 }} data-masked={masked}>
          {view.todo_masked_text}
        </p>
      ) : null}
    </section>
  );
}
