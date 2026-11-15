/** İskelet: ekran ekipleri kendi branch'lerinde bu yer tutucuların yerine gerçek ekranı koyar. */
import type { StationInfo } from "../api/station";
import { type Lang, LangSwitch, useLang } from "./i18n";

export interface PlaceholderProps {
  station: StationInfo;
  title: Record<Lang, string>;
  intro: Record<Lang, string>;
  endpoints: string[];
}

export function Placeholder({ station, title, intro, endpoints }: PlaceholderProps) {
  const { lang, t } = useLang();
  return (
    <div className="mx-auto max-w-3xl space-y-5 px-4 py-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm text-slate-400">
            {t("appTitle")} · {t(station.role)} · v{station.version}
          </p>
          <h1 className="text-2xl font-bold">{title[lang]}</h1>
        </div>
        <LangSwitch />
      </header>
      <p className="rounded-lg border border-dashed border-slate-600 p-4 text-slate-300">
        <span className="mr-2 rounded bg-slate-700 px-2 py-0.5 text-xs font-semibold uppercase">{t("placeholder")}</span>
        {intro[lang]}
      </p>
      <section>
        <h2 className="mb-2 font-semibold">API</h2>
        <ul className="space-y-1 font-mono text-sm text-slate-300">
          {endpoints.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
        <p className="mt-3 text-sm">
          <a className="text-sky-400 underline" href="/docs">
            /docs
          </a>{" "}
          · <code className="text-slate-400">frontend/src/api/station.ts</code>
        </p>
      </section>
    </div>
  );
}
