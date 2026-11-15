/**
 * Canlı bağlantı: Dünya backend'inin yerel SSE akışı (/api/stream/monitor).
 *
 * - `event`: gemiden yeni bir olay Dünya'ya ulaştı → ilgili sorgular yenilenir, kart/satır kısa süre vurgulanır.
 * - `link`:  bağlantı durumu (heartbeat aralığında da gelir) → bağlantı çubuğu.
 * Gemi kapanırsa son veri ekranda kalır (sorgular eski veriyi tutar); bağlantı gelince Dünya alıcısı
 * kaldığı seq'ten devam eder, yeni olaylar bu akıştan gelir. Bağlantı geçişleri akışa ekran işareti olarak düşer.
 *
 * Geminin saati: bağlantı bilgisi geminin şu anki saatini taşır (`LinkStatus.ship_clock`); ekran saatiyle farkı
 * (`shipOffsetMs`) tutulur. Gemi saatiyle gelen zamanlar ("son görülme", "son etkinlik") `useShipNow` ile
 * karşılaştırılır: yerel ağda bilgisayar saatleri kaysa da doğru kalır.
 */
import { useQueryClient } from "@tanstack/react-query";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import type { LinkStatus, MonitorStreamEvent } from "../../api/station";
import { monitorStreamUrl, qk, useLinkStatus } from "./api";
import { HIGHLIGHT_MS } from "./config";

export interface LinkMarker {
  kind: "link";
  up: boolean;
  at: string; // ekranın saati (ISO)
  id: number;
}

interface Flash {
  seq: number;
  until: number;
}

interface LiveCtx {
  link: LinkStatus | undefined;
  /** Dünya sunucusuna (bu istasyon) ulaşılabiliyor mu */
  earthReachable: boolean;
  /** Son başarılı bağlantı bilgisi (ekran saati, ms) */
  linkUpdatedAt: number;
  markers: LinkMarker[];
  /** Vurgu: astronot → son olayın seq'i (süre dolunca silinir) */
  flashFor: (astronautId: string) => number | null;
  flashSeq: (seq: number) => boolean;
  /** Geminin saati − ekranın saati (ms); gemiden henüz haber yoksa 0 */
  shipOffsetMs: number;
}

const Ctx = createContext<LiveCtx | null>(null);

export function LiveProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const linkQ = useLinkStatus();
  const [streamUp, setStreamUp] = useState(true);
  const [flashes, setFlashes] = useState<Record<string, Flash>>({});
  const [seqFlashes, setSeqFlashes] = useState<Record<number, number>>({});
  const [markers, setMarkers] = useState<LinkMarker[]>([]);
  const [shipOffsetMs, setShipOffsetMs] = useState(0);
  const epochRef = useRef<string | null | undefined>(undefined);
  const connectedRef = useRef<boolean | undefined>(undefined);
  const markerId = useRef(0);

  const onEvent = useCallback(
    (ev: MonitorStreamEvent) => {
      void qc.invalidateQueries({ queryKey: ["monitor", "crew"] });
      void qc.invalidateQueries({ queryKey: ["monitor", "events"] });
      // Terminal olayları (terminal.*) gün taşımaz: şerit ve gün yeniden okunmaz
      if (ev.astronaut_id && !ev.type?.startsWith("terminal.")) {
        void qc.invalidateQueries({ queryKey: qk.overviewAny(ev.astronaut_id) });
        void qc.invalidateQueries({ queryKey: qk.dayAny(ev.astronaut_id) });
      }
      const until = Date.now() + HIGHLIGHT_MS;
      const seq = ev.seq ?? 0;
      if (ev.astronaut_id) setFlashes((f) => ({ ...f, [ev.astronaut_id as string]: { seq, until } }));
      if (seq) setSeqFlashes((f) => ({ ...f, [seq]: until }));
    },
    [qc],
  );

  // SSE: EventSource kendisi yeniden bağlanır (Dünya sunucusu yeniden başlarsa da)
  useEffect(() => {
    const es = new EventSource(monitorStreamUrl());
    let failed = false;
    es.onopen = () => {
      setStreamUp(true);
      // Dünya sunucusu geri geldi (ör. yeniden başladı): kaçan her şeyi baştan oku
      if (failed) void qc.invalidateQueries({ queryKey: qk.all });
      failed = false;
    };
    es.onerror = () => {
      failed = true;
      setStreamUp(false);
      void qc.invalidateQueries({ queryKey: qk.link() }); // ulaşılamıyorsa bağlantı sorgusu hata verir
    };
    es.addEventListener("link", (e) => {
      try {
        const data = JSON.parse((e as MessageEvent).data) as MonitorStreamEvent;
        if (data.link) qc.setQueryData(qk.link(), data.link);
        setStreamUp(true);
      } catch {
        /* bozuk olay: yok say */
      }
    });
    es.addEventListener("event", (e) => {
      try {
        onEvent(JSON.parse((e as MessageEvent).data) as MonitorStreamEvent);
      } catch {
        /* bozuk olay: yok say */
      }
    });
    return () => es.close();
  }, [qc, onEvent]);

  // Dönem değişti (gemi verisi sıfırlandı → snapshot) veya bağlantı durumu değişti
  const link = linkQ.data;
  useEffect(() => {
    if (!link) return;
    // Geminin saati: cevabın üretildiği andaki tahmin; 1 sn'den küçük oynamalar yok sayılır (gereksiz çizim olmasın)
    if (link.ship_clock) {
      const off = new Date(link.ship_clock).getTime() - Date.now();
      setShipOffsetMs((prev) => (Math.abs(prev - off) > 1000 ? off : prev));
    }
    if (epochRef.current !== undefined && epochRef.current !== link.epoch) void qc.invalidateQueries({ queryKey: qk.all });
    epochRef.current = link.epoch;
    const was = connectedRef.current;
    connectedRef.current = link.connected;
    if (was !== undefined && was !== link.connected) {
      setMarkers((m) => [{ kind: "link" as const, up: link.connected, at: new Date().toISOString(), id: ++markerId.current }, ...m].slice(0, 20));
      if (link.connected) {
        void qc.invalidateQueries({ queryKey: ["monitor", "crew"] });
        void qc.invalidateQueries({ queryKey: ["monitor", "events"] });
      }
    }
  }, [link, qc]);

  // Süresi dolan vurguları temizle
  useEffect(() => {
    const times = [...Object.values(flashes).map((f) => f.until), ...Object.values(seqFlashes)];
    if (!times.length) return;
    const wait = Math.max(50, Math.min(...times) - Date.now());
    const h = window.setTimeout(() => {
      const now = Date.now();
      setFlashes((f) => Object.fromEntries(Object.entries(f).filter(([, v]) => v.until > now)));
      setSeqFlashes((f) => Object.fromEntries(Object.entries(f).filter(([, v]) => v > now)) as Record<number, number>);
    }, wait);
    return () => window.clearTimeout(h);
  }, [flashes, seqFlashes]);

  const earthReachable = !linkQ.isError && (streamUp || linkQ.isSuccess);
  const reachableRef = useRef(earthReachable);
  useEffect(() => {
    if (earthReachable && !reachableRef.current) void qc.invalidateQueries({ queryKey: qk.all });
    reachableRef.current = earthReachable;
  }, [earthReachable, qc]);
  const value = useMemo<LiveCtx>(
    () => ({
      link,
      earthReachable,
      linkUpdatedAt: linkQ.dataUpdatedAt,
      markers,
      flashFor: (id) => flashes[id]?.seq ?? null,
      flashSeq: (seq) => seq in seqFlashes,
      shipOffsetMs,
    }),
    [link, earthReachable, linkQ.dataUpdatedAt, markers, flashes, seqFlashes, shipOffsetMs],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLive(): LiveCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useLive: LiveProvider yok");
  return v;
}

/** Saniyede bir güncellenen "şimdi" (son temas X sn önce). */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const h = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(h);
  }, [intervalMs]);
  return now;
}

/**
 * Geminin şu anki saati (ms). Bileşen en az `intervalMs`'te bir yeniden çizilir; değer her çizimin anıdır (veri
 * aralığın ortasında gelirse — ör. terminal çevrimdışı oldu — "… önce" bir önceki tikten değil, o andan hesaplanır).
 */
export function useShipNow(intervalMs = 1000): number {
  useNow(intervalMs);
  return Date.now() + useLive().shipOffsetMs;
}

/** Vurgu sınıfı: aynı öğeye üst üste olay gelirse animasyon yeniden başlasın diye seq'in paritesi. */
export const flashClass = (seq: number | null): string => (seq === null ? "" : ` flash flash-${seq % 2}`);
