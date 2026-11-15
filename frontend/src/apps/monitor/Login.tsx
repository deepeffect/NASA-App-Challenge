/** Dünya üssü girişi (EARTH / EARTH). Prototipteki giriş kartıyla aynı düzen; ipucu ve hatalar backend'den. */
import { useQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { StationApiError, stationApi } from "../../api/station";
import { useLang } from "../../shared/i18n";
import { PRODUCT_NAME } from "./config";
import { Logo } from "./icons";
import { useT } from "./texts";

export function Login({ onDone }: { onDone: () => void }) {
  const { t } = useT();
  const { lang } = useLang();
  const hint = useQuery({ queryKey: ["monitor", "hint", lang], queryFn: stationApi.hint, retry: 1 });
  const [id, setId] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!id.trim()) return setErr(t("enterId"));
    setBusy(true);
    setErr(null);
    try {
      await stationApi.login(id.trim(), pw.trim());
      onDone();
    } catch (ex) {
      setErr(ex instanceof StationApiError ? ex.message : t("serverDown"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <section className="card login" aria-labelledby="login-h">
        <div className="brand">
          <Logo />
          <div>
            <p className="muted">{PRODUCT_NAME[lang]}</p>
            <h1 id="login-h">{t("loginTitle")}</h1>
          </div>
        </div>
        <p className="ink2">{t("loginIntro")}</p>
        <form onSubmit={submit} noValidate>
          <div className="field">
            <label htmlFor="mon-id">{t("id")}</label>
            <input id="mon-id" autoComplete="off" autoCapitalize="characters" spellCheck={false} placeholder="EARTH" value={id} onChange={(e) => setId(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="mon-pw">{t("password")}</label>
            <input id="mon-pw" type="password" autoComplete="off" value={pw} onChange={(e) => setPw(e.target.value)} />
          </div>
          <button type="submit" className="primary" disabled={busy}>
            {busy ? t("loggingIn") : t("login")}
          </button>
        </form>
        {err && (
          <p className="err" role="alert">
            {err}
          </p>
        )}
        {hint.data && <p>{hint.data.text}</p>}
        {hint.isError && <p className="err">{t("serverDown")}</p>}
        <p className="muted">{t("demoLogin")}</p>
      </section>
    </div>
  );
}
