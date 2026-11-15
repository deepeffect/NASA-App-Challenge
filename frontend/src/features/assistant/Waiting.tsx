import { useEffect, useState } from "react";

import { useAssistantTexts } from "./texts";

/**
 * Yerel model yavaş: geçen süreyi gösteren yükleniyor göstergesi.
 * Bilerek `data-spinner` taşımaz: smoke'un settle() beklemesi harici asistan API'sini (10–30 sn) beklemesin.
 */
export function Waiting({ label }: { label: string }) {
  const t = useAssistantTexts();
  const [sec, setSec] = useState(0);
  useEffect(() => {
    const t0 = Date.now();
    const id = setInterval(() => setSec(Math.floor((Date.now() - t0) / 1000)), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="flex items-center gap-3 text-slate-400" role="status" data-assistant-waiting="">
      <span className="h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-slate-600 border-t-sky-400" />
      <span>
        {label} <span className="tabular-nums">{sec} s</span>
        <span className="block text-sm text-slate-500">{t("modelNote")}</span>
      </span>
    </div>
  );
}

/** Asistan seçimi hazır değilse (senkronlanıyor / veri yok / hata) kart içeriği yerine gösterilir. */
export function SelectionPending({ status, message, astronautId, day }: {
  status: string; message?: string; astronautId: string; day: number | null;
}) {
  const t = useAssistantTexts();
  if (status === "syncing") {
    return <Waiting label={t("selecting", { id: astronautId, day: day != null ? t("dayPart", { day }) : "" })} />;
  }
  return <p className="text-slate-400">ⓘ {message ?? t("notAvailable")}</p>;
}
