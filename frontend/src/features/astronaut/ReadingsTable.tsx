/**
 * "Bu günün ölçümleri": her metriğin son değeri, kişisel normali, 7 günlük sapması, katalogdaki
 * normal aralığı ve durumu. Durum renkle değil ikon + metinle verilir. Satıra tıklayınca metrik
 * grafiği o metriğe geçer. Değerlerin tamamı API'den gelir (summary.latest + metrik kataloğu).
 */
import type { MetricInfo, MetricSnapshot, SystemScore } from "../../api/client";
import { useCatalog } from "../../api/queries";
import { fmtNum, unitLabel } from "../../components/ui/format";
import { AlertTriangleIcon, CheckCircleIcon, HelpCircleIcon, InfoIcon } from "../../components/ui/icons";

const STATE = {
  normal: { label: "Normal", cls: "text-emerald-300", Icon: CheckCircleIcon },
  watch: { label: "İzlem", cls: "text-sky-300", Icon: InfoIcon },
  alert: { label: "Uyarı", cls: "text-orange-300", Icon: AlertTriangleIcon },
  no_data: { label: "Veri yok", cls: "text-slate-400", Icon: HelpCircleIcon },
} as const;

function rangeText(info: MetricInfo | undefined): string {
  const r = info?.normal_range;
  if (!r || (r.low == null && r.high == null)) return "—";
  const d = info.decimals;
  if (r.low != null && r.high != null) return `${fmtNum(r.low, d)} – ${fmtNum(r.high, d)}`;
  return r.low != null ? `${fmtNum(r.low, d)} ve üzeri` : `${fmtNum(r.high, d)} ve altı`;
}

export function ReadingsTable({
  latest,
  systems,
  selectedMetric,
  onShowMetric,
}: {
  latest: MetricSnapshot[];
  systems: SystemScore[];
  selectedMetric: string | null;
  onShowMetric: (metric: string) => void;
}) {
  const catalog = useCatalog();
  const info = (name: string) => catalog.data?.metrics.find((m) => m.name === name);
  const unverified = latest.some((m) => !m.threshold_verified);

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[13.5px]">
          <thead>
            <tr className="text-left text-xs font-semibold text-slate-400">
              <th className="border-b border-slate-800 px-2 py-1.5">Ölçüm</th>
              <th className="border-b border-slate-800 px-2 py-1.5 text-right">Son değer</th>
              <th className="border-b border-slate-800 px-2 py-1.5 text-right">Kişisel normal</th>
              <th className="border-b border-slate-800 px-2 py-1.5 text-right">7 gün z</th>
              <th className="border-b border-slate-800 px-2 py-1.5">Normal aralık</th>
              <th className="border-b border-slate-800 px-2 py-1.5">Durum</th>
            </tr>
          </thead>
          <tbody>
            {systems.map((sys) => {
              const rows = latest.filter((m) => m.system === sys.system);
              if (!rows.length) return null;
              return [
                <tr key={sys.system}>
                  <td colSpan={6} className="border-b border-slate-300 px-2 pb-1.5 pt-3 font-[family-name:var(--font-display)] font-semibold">
                    {sys.display_name}
                  </td>
                </tr>,
                ...rows.map((m) => {
                  const mi = info(m.metric);
                  const d = mi?.decimals ?? 1;
                  const st = STATE[m.state];
                  const active = m.metric === selectedMetric;
                  return (
                    <tr key={m.metric} className={active ? "bg-sky-950" : "hover:bg-slate-950"}>
                      <td className="min-w-36 border-b border-slate-800 px-2 py-1.5">
                        <button
                          type="button"
                          onClick={() => onShowMetric(m.metric)}
                          className="text-left underline decoration-slate-600 underline-offset-2 hover:decoration-sky-400"
                          aria-label={`${m.display_name} grafiğini göster`}
                          aria-pressed={active}
                        >
                          {m.display_name}
                        </button>{" "}
                        <span className="text-slate-500">{unitLabel(m.unit)}</span>
                      </td>
                      <td className="num whitespace-nowrap border-b border-slate-800 px-2 py-1.5 text-right">{fmtNum(m.value, d)}</td>
                      <td className="num whitespace-nowrap border-b border-slate-800 px-2 py-1.5 text-right">{fmtNum(m.baseline_mean, d)}</td>
                      <td className="num whitespace-nowrap border-b border-slate-800 px-2 py-1.5 text-right">{fmtNum(m.z7, 1)}</td>
                      <td className="num whitespace-nowrap border-b border-slate-800 px-2 py-1.5">{rangeText(mi)}</td>
                      <td className="whitespace-nowrap border-b border-slate-800 px-2 py-1.5">
                        <span className={`inline-flex items-center gap-1.5 font-medium ${st.cls}`}>
                          <st.Icon className="h-4 w-4" />
                          {st.label}
                        </span>
                      </td>
                    </tr>
                  );
                }),
              ];
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2.5 max-w-[80ch] text-[13px] text-slate-400">
        Durum, aktif olaylardan gelir (eşik aşımı, kişisel normalden sapma, hızlı kötüleşme). “7 gün z”, son 7 günün
        ortalamasının kişisel normalden kaç standart sapma uzakta olduğunu gösterir.
        {unverified && " Eşikler ve normal aralıklar doğrulanmamış yer tutuculardır."}
      </p>
    </div>
  );
}
