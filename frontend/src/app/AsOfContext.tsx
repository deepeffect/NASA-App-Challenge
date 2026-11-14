/** Global zaman kaydırıcısı durumu: `asOf` = null → canlı (verideki son gün). */
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

interface AsOfState {
  asOf: string | null;
  setAsOf: (d: string | null) => void;
}

const AsOfCtx = createContext<AsOfState | null>(null);

export function AsOfProvider({ children }: { children: ReactNode }) {
  const [asOf, setAsOf] = useState<string | null>(null);
  const value = useMemo(() => ({ asOf, setAsOf }), [asOf]);
  return <AsOfCtx.Provider value={value}>{children}</AsOfCtx.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAsOf(): AsOfState {
  const v = useContext(AsOfCtx);
  if (!v) throw new Error("useAsOf, AsOfProvider içinde kullanılmalı");
  return v;
}
