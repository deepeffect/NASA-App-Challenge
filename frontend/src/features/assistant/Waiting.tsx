import { useEffect, useState } from "react";

/**
 * Yerel model yavaş: geçen süreyi gösteren yükleniyor göstergesi.
 * Bilerek `data-spinner` taşımaz: smoke'un settle() beklemesi harici asistan API'sini (10–30 sn) beklemesin.
 */
export function Waiting({ label }: { label: string }) {
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
        <span className="block text-sm text-slate-500">The model runs onboard; answers can take 10–30 s.</span>
      </span>
    </div>
  );
}
