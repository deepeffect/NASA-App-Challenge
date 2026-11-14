/** Acil belirti bandı — kural tabanlı `emergency` olayı/cevabı için. Sohbet ve check-in ortak kullanır. */
import type { EmergencyNotice } from "../../api/client";
import { OctagonAlertIcon } from "./icons";

export function EmergencyBanner({ notice, onDismiss }: { notice: EmergencyNotice; onDismiss?: () => void }) {
  return (
    <div role="alert" aria-live="assertive" className="rounded-2xl border-2 border-red-500 bg-red-950 p-5 text-red-50 shadow-lg shadow-red-950/50">
      <div className="flex items-start gap-3">
        <OctagonAlertIcon className="mt-0.5 h-8 w-8 shrink-0 text-red-300" />
        <div className="space-y-3">
          <p className="text-xl font-bold">ACİL: {notice.protocol.title}</p>
          <p className="text-lg">{notice.message}</p>
          <ol className="list-decimal space-y-1 pl-6 text-lg">
            {notice.protocol.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
          <p className="text-base text-red-200">İletişim: {notice.protocol.contacts.join(" · ")}</p>
          {!notice.protocol.verified && (
            <p className="text-sm text-red-300">
              Not: Protokol metni placeholder'dır, mürettebat tıbbi prosedürleriyle doğrulanmamıştır.
            </p>
          )}
          {onDismiss && (
            <button type="button" onClick={onDismiss} className="text-sm text-red-200 underline underline-offset-4">
              Bandı gizle (protokol devam ediyor)
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
