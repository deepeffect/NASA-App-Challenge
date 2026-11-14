/**
 * Günlük check-in kartı. Prototip: <section aria-label="Daily check-in"> + renderCheckin() / ciSend().
 *
 * Farklar:
 *  - Kayıt tarayıcıda (localStorage) değil gemidedir: her cevap `POST /api/checkin/turn`, paylaşım
 *    `POST /api/checkin/share`, baştan başlama `POST /api/checkin/reset`. Sorular, hızlı cevaplar, cevaplar,
 *    notlar ve paylaşım açıklamaları backend'den gelir.
 *  - Check-in sadece bugün yapılır. Geçmiş bir gün seçiliyken o günün kaydedilmiş check-in'i salt okunur görünür.
 *  - "Scripted questions for now…" cümlesinin yerinde aktif mod satırı vardır (`mode_text`):
 *    "Asistan: Qwen" veya "Hazır sorular, model çevrim dışı".
 *  - Acil belirti: "Gemideki sağlık sorumlusu bilgilendirildi" kutusu (`cmo_notice`). Bu bilgi Dünya'ya gitmez.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useRef, useState } from "react";

import { type CheckinState, type ShareLevel, StationApiError, stationApi } from "../../api/station";
import { Glyph } from "../../shared/health";
import { dropOtherLanguages, isUnauthorized, qk, useCheckin } from "./api";
import { useT } from "./texts";

export function CheckinCard({ day }: { day: number }) {
  const { t, lang } = useT();
  const qc = useQueryClient();
  const checkin = useCheckin(day, lang);
  const inputRef = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState("");
  const [failed, setFailed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Değişiklik sonrası: yeni durum seçili dilin önbelleğine yazılır; günün görünümü (paylaşım seviyesi) tazelenir.
  const store = (state: CheckinState) => {
    qc.setQueryData(qk.checkin(state.day, lang), state);
    dropOtherLanguages(qc, qk.checkinAny(state.day), lang);
    void qc.invalidateQueries({ queryKey: qk.dayAny(state.day) });
  };
  const onError = (e: unknown) => {
    if (!isUnauthorized(e)) setError(e instanceof StationApiError ? e.message : t("sendFailed")); // 401: uygulama girişe döner
  };

  const turn = useMutation({
    mutationFn: (answer: string) => stationApi.turn(answer),
    onMutate: () => {
      setFailed(false);
      setError(null);
    },
    onSuccess: (out) => store(out.checkin),
    onError: (e) => {
      // Prototipteki gibi: cevap gitmediyse sohbet kilitlenmez, yeniden cevaplanır.
      if (e instanceof StationApiError && e.status < 500) {
        onError(e);
        void checkin.refetch(); // örn. check-in başka bir sekmede bitmiş
      } else setFailed(true);
    },
  });
  const share = useMutation({
    mutationFn: (level: ShareLevel) => stationApi.share(level),
    onMutate: () => setError(null),
    onSuccess: store,
    onError,
  });
  const reset = useMutation({
    mutationFn: () => stationApi.resetCheckin(),
    onMutate: () => {
      setFailed(false);
      setError(null);
    },
    onSuccess: store,
    onError,
  });

  const st = checkin.data;
  const busy = turn.isPending || share.isPending || reset.isPending;

  const send = (text: string) => {
    const answer = text.trim();
    if (!answer || !st?.editable || busy) return;
    setDraft("");
    turn.mutate(answer);
    inputRef.current?.focus(); // hızlı cevap düğmesi kaybolunca odak kaybolmasın
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    send(draft);
  };

  return (
    <section className="card" aria-label={t("checkinTitle")} data-day={day}>
      <div className="ci-head">
        <h2>{t("checkinTitle")}</h2>
        {st?.can_reset ? (
          <button type="button" className="linkbtn" disabled={busy} onClick={() => reset.mutate()}>
            {t("startOver")}
          </button>
        ) : null}
      </div>

      {!st ? (
        checkin.isError ? (
          <p className="err" role="alert" style={{ marginTop: 8 }}>
            {t("loadError")}
            <button type="button" onClick={() => void checkin.refetch()}>
              {t("retry")}
            </button>
          </p>
        ) : (
          <p className="waiting" style={{ marginTop: 8 }}>
            {t("loading")}
          </p>
        )
      ) : (
        <>
          {!st.is_today && !st.started ? (
            <p className="calm" style={{ marginTop: 8 }}>
              {t("pastNoCheckin")}
            </p>
          ) : (
            <div className="cilog" aria-live="polite">
              {st.messages.map((m, i) => (
                <div key={i} className={`msg ${m.who}`}>
                  {m.text}
                </div>
              ))}
              {turn.isPending ? <div className="msg me pending">{turn.variables}</div> : null}
              {failed ? <div className="msg bot">{t("sendFailed")}</div> : null}
            </div>
          )}

          {st.is_today ? (
            <form onSubmit={onSubmit}>
              <div className="chips">
                {st.editable
                  ? st.options.map((option) => (
                      <button key={option} type="button" disabled={busy} onClick={() => send(option)}>
                        {option}
                      </button>
                    ))
                  : null}
              </div>
              <div className="cirow">
                <input
                  ref={inputRef}
                  type="text"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  disabled={!st.editable}
                  placeholder={st.editable ? t("answerPlaceholder") : t("answerDone")}
                  autoComplete="off"
                  aria-label={t("answerLabel")}
                  maxLength={2000}
                />
                <button type="submit" disabled={!st.editable || busy}>
                  {t("send")}
                </button>
              </div>
            </form>
          ) : null}

          {st.notes.length > 0 ? (
            <div className="cinotes">
              {st.notes.map((note, i) => (
                <div key={i}>
                  <span className="t">{note.topic}</span>
                  <span>{note.text}</span>
                  {note.flag ? (
                    <>
                      <Glyph level={1} small />
                      <span className="muted">{t("flagged")}</span>
                    </>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}

          {st.cmo_notice ? (
            <p className="ground" style={{ marginTop: 12 }} data-cmo>
              <b>{st.cmo_notice.title}</b> {st.cmo_notice.text}
            </p>
          ) : null}

          {st.done && st.is_today && st.share_options.length > 0 ? (
            <div className="share">
              <b>{t("shareQuestion")}</b>
              <div className="chips">
                {st.share_options.map((option) => (
                  <button
                    key={option.level}
                    type="button"
                    data-level={option.level}
                    aria-pressed={option.selected}
                    disabled={!option.enabled || busy}
                    onClick={() => {
                      if (!option.selected) share.mutate(option.level);
                    }}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
              <p className="muted">{st.share_note}</p>
              <p className="muted">{st.share_cmo_note}</p>
            </div>
          ) : null}

          {!st.is_today && st.share ? (
            <p className="muted" style={{ marginTop: 10 }}>
              {t("sharedLevel", { level: st.share_options.find((o) => o.selected)?.label ?? st.share })}
            </p>
          ) : null}

          {error ? (
            <p className="err" role="alert" style={{ marginTop: 10 }}>
              {error}
            </p>
          ) : null}

          <p className="muted" style={{ marginTop: 10 }}>
            {st.is_today ? (
              <>
                {t("answersStay")} <span data-mode={st.mode}>{st.mode_text}</span>.
              </>
            ) : (
              t("pastReadOnly")
            )}
          </p>
        </>
      )}
    </section>
  );
}
