/**
 * Arayüz dili (tr | en). Seçim tarayıcıda saklanır; yeni API istemcisi her isteğe `lang`'ı açıkça ekler
 * (backend: ?lang= > Accept-Language > tr).
 */
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type Lang = "tr" | "en";
const KEY = "ahm-lang";

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "tr" || saved === "en") return saved;
  } catch {
    /* depolama kapalı olabilir */
  }
  return navigator.language?.toLowerCase().startsWith("en") ? "en" : "tr";
}

let current: Lang = initialLang();
/** React dışı kod (API istemcisi) için geçerli dil. */
export const currentLang = (): Lang => current;

// Sadece iskelet ekranların metinleri; ekran ekipleri kendi metinlerini ekler.
const TEXTS = {
  appTitle: { tr: "Astronot Sağlık İzleme", en: "Astronaut Health Monitor" },
  ship: { tr: "Gemi", en: "Ship" },
  earth: { tr: "Dünya üssü", en: "Earth base" },
  loading: { tr: "Yükleniyor…", en: "Loading…" },
  backendDown: { tr: "Bu istasyonun sunucusuna ulaşılamıyor.", en: "Cannot reach this station's server." },
  notOnStationTitle: { tr: "Bu ekran bu istasyonda değil", en: "This screen is not on this station" },
  notOnStationText: {
    tr: "Bu bilgisayar: {station}. Bu istasyonun ekranı:",
    en: "This computer is the {station}. This station's screen is:",
  },
  legacyOff: {
    tr: "Eski ekranlar sadece gemide ve DATA_SOURCE=synthetic iken çalışır.",
    en: "The legacy screens only run on the ship with DATA_SOURCE=synthetic.",
  },
  notFound: { tr: "Sayfa bulunamadı.", en: "Page not found." },
  language: { tr: "Dil", en: "Language" },
  placeholder: { tr: "Yer tutucu", en: "Placeholder" },
} as const;
export type TextKey = keyof typeof TEXTS;

interface LangCtx {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: TextKey, vars?: Record<string, string>) => string;
}
const Ctx = createContext<LangCtx | null>(null);

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(current);
  const setLang = useCallback((l: Lang) => {
    current = l;
    setLangState(l);
    try {
      localStorage.setItem(KEY, l);
    } catch {
      /* yok say */
    }
  }, []);
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  const value = useMemo<LangCtx>(
    () => ({
      lang,
      setLang,
      t: (key, vars) => Object.entries(vars ?? {}).reduce((s, [k, v]) => s.replace(`{${k}}`, v), TEXTS[key][lang] as string),
    }),
    [lang, setLang],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLang(): LangCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useLang: LangProvider yok");
  return v;
}

export function LangSwitch() {
  const { lang, setLang, t } = useLang();
  return (
    <div className="flex items-center gap-1 text-sm" role="group" aria-label={t("language")}>
      {(["tr", "en"] as const).map((l) => (
        <button
          key={l}
          type="button"
          onClick={() => setLang(l)}
          aria-pressed={lang === l}
          className={`rounded-md px-2 py-1 ${lang === l ? "bg-slate-700 text-slate-50" : "text-slate-400 hover:bg-slate-800"}`}
        >
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
