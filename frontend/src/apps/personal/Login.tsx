/**
 * Giriş kartı. Prototip: <section class="card login">.
 * Farklar: giriş `POST /api/auth/login` ile yapılır; kimlik aralığı `GET /api/auth/hint`'ten gelir; bu ekranda
 * EARTH girişi yoktur (Dünya üssü kendi istasyonundan girer — backend de reddeder ve nedenini söyler).
 * Hata metinleri backend'den seçili dilde gelir.
 */
import { type FormEvent, type ReactElement, type ReactNode, useState } from "react";

import { type AuthHint, StationApiError, stationApi } from "../../api/station";
import { useHint } from "./api";
import { useT } from "./texts";

/** İpucu cümlesindeki ilk ve son kimliği prototipteki gibi kalın yazar (cümlenin kendisi backend'den gelir). */
function hintWithBoldIds(hint: AuthHint): ReactNode {
  const ids = hint.astronauts ? [hint.astronauts.first_id, hint.astronauts.last_id] : [];
  let parts: (string | ReactElement)[] = [hint.text];
  for (const id of new Set(ids)) {
    const next: (string | ReactElement)[] = [];
    parts.forEach((part, i) => {
      if (typeof part !== "string") {
        next.push(part);
        return;
      }
      part.split(id).forEach((piece, k) => {
        if (k > 0) next.push(<b key={`${id}-${i}-${k}`}>{id}</b>);
        next.push(piece);
      });
    });
    parts = next;
  }
  return parts;
}

export function Login({ notice, onDone }: { notice: string | null; onDone: () => void }) {
  const { t, lang } = useT();
  const hint = useHint(lang);
  const [id, setId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    if (!id.trim()) return setError(t("enterId"));
    setBusy(true);
    setError(null);
    try {
      await stationApi.login(id.trim(), password.trim());
      onDone();
    } catch (ex) {
      setError(ex instanceof StationApiError ? ex.message : t("serverDown"));
    } finally {
      setBusy(false);
    }
  };

  const message = error ?? notice;
  return (
    <section className="card login" aria-label={t("loginTitle")}>
      <h2>{t("loginTitle")}</h2>
      <form onSubmit={submit} noValidate>
        <div className="field">
          <label htmlFor="me-id">{t("idLabel")}</label>
          <input
            id="me-id"
            type="text"
            value={id}
            onChange={(e) => setId(e.target.value)}
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            placeholder={hint.data?.astronauts?.first_id ?? ""}
          />
        </div>
        <div className="field">
          <label htmlFor="me-pw">{t("pwLabel")}</label>
          <input
            id="me-pw"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="off"
            placeholder={t("pwPlaceholder")}
          />
        </div>
        <button type="submit" className="primary" disabled={busy}>
          {t("loginButton")}
        </button>
      </form>
      {message ? (
        <p className="err" role="alert">
          {message}
        </p>
      ) : null}
      {hint.data ? <p>{hintWithBoldIds(hint.data)}</p> : hint.isError ? <p className="err">{t("serverDown")}</p> : null}
      <p className="muted">{t("demoNote")}</p>
    </section>
  );
}
