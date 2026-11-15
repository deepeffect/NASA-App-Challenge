/** Üst başlık (logo, ürün adı, dil, tema, çıkış) ve alt bilgi. */
import type { StationInfo } from "../../api/station";
import { type Lang, useLang } from "../../shared/i18n";
import { useMissionLabel } from "./api";
import { DEMO_CREW, EVENT_NAME, MISSION, PRODUCT_NAME, TEAM_NAME } from "./config";
import { Logo, LogoutIcon, MoonIcon, SunIcon } from "./icons";
import { useT } from "./texts";
import type { Theme } from "./ui";

export function Header({ theme, setTheme, onLogout }: { theme: Theme; setTheme: (t: Theme) => void; onLogout: () => void }) {
  const { t } = useT();
  const { lang } = useLang();
  const missionLabel = useMissionLabel(MISSION.id);
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <header className="mon-head">
      <div className="mon-brand">
        <Logo />
        <div>
          <h1>{PRODUCT_NAME[lang]}</h1>
          <p className="who">
            {t("earthBase")} · {t("readOnly")}
          </p>
        </div>
      </div>
      <span className="spacer" />
      <p className="mission" data-mission={MISSION.id}>
        <span>{t("missionLabel")}</span>
        <b aria-busy={missionLabel === undefined}>{missionLabel ?? "…"}</b>
        <span className="muted">· {t("crewCount", { n: DEMO_CREW.length })}</span>
      </p>
      <span className="spacer" />
      <div className="mon-tools">
        <LangSeg />
        <button
          type="button"
          className="icon-btn"
          onClick={() => setTheme(next)}
          aria-label={next === "light" ? t("themeLight") : t("themeDark")}
          title={next === "light" ? t("themeLight") : t("themeDark")}
        >
          {next === "light" ? <SunIcon /> : <MoonIcon />}
        </button>
        <button type="button" className="icon-btn" onClick={onLogout} aria-label={t("logout")} title={t("logout")}>
          <LogoutIcon />
        </button>
      </div>
    </header>
  );
}

export function LangSeg() {
  const { lang, setLang } = useLang();
  const { t } = useT();
  return (
    <div className="seg" role="group" aria-label={t("language")}>
      {(["tr", "en"] as Lang[]).map((l) => (
        <button key={l} type="button" aria-pressed={lang === l} onClick={() => setLang(l)} lang={l}>
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

export function Footer({ station }: { station: StationInfo }) {
  const { t } = useT();
  return (
    <footer className="mon-foot">
      <span>{t("footer", { event: EVENT_NAME, team: TEAM_NAME })}</span>
      <span>
        {t("simNote")} · v{station.version}
      </span>
    </footer>
  );
}
