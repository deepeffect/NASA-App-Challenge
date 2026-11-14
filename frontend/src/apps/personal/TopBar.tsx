/**
 * Üst bar. Prototip: <div class="top"> (başlık · kim + Çıkış · i düğmesi). Ek: TR/EN seçimi.
 * Giriş ekranında da görünür: dil seçimi ve "tüm öz bakım çözümleri" girişten önce de kullanılabilir.
 */
import { useT } from "./texts";

export interface TopBarProps {
  /** Giriş yapan astronot, örn. "A000 · Mars yüzeyi"; giriş yoksa null. */
  who: string | null;
  authed: boolean;
  onLogout: () => void;
  onInfo: () => void;
}

export function TopBar({ who, authed, onLogout, onInfo }: TopBarProps) {
  const { t, lang, setLang } = useT();
  return (
    <div className="top">
      <h1>{t("title")}</h1>
      <div className="pick">
        {who ? <span className="whoami">{who}</span> : null}
        {authed ? (
          <button type="button" onClick={onLogout}>
            {t("logout")}
          </button>
        ) : null}
        <div className="langseg" role="group" aria-label={t("language")}>
          {(["tr", "en"] as const).map((l) => (
            <button key={l} type="button" lang={l} aria-pressed={lang === l} onClick={() => setLang(l)}>
              {l.toUpperCase()}
            </button>
          ))}
        </div>
      </div>
      <button type="button" className="infobtn" aria-label={t("allSolutions")} title={t("allSolutions")} onClick={onInfo}>
        i
      </button>
    </div>
  );
}
