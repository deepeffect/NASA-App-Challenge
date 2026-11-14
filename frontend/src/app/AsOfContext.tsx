/**
 * Global zaman kaydırıcısı durumu: `asOf` = null → canlı (verideki son gün).
 * URL ile senkron (`?as_of=YYYY-MM-DD`): link paylaşılabilir, geri/ileri çalışır,
 * sayfalar arası gezinmede seçili gün korunur.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";

interface AsOfState {
  asOf: string | null;
  setAsOf: (d: string | null) => void;
}

const AsOfCtx = createContext<AsOfState | null>(null);
const PARAM = "as_of";

function readParam(search: string): string | null {
  const v = new URLSearchParams(search).get(PARAM);
  return v && /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : null;
}

function withParam(search: string, asOf: string | null): string {
  const sp = new URLSearchParams(search);
  if (asOf) sp.set(PARAM, asOf);
  else sp.delete(PARAM);
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export function AsOfProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [asOf, setState] = useState<string | null>(() => readParam(location.search));
  const locRef = useRef(location);
  locRef.current = location;

  const setAsOf = useCallback(
    (d: string | null) => {
      setState(d);
      const loc = locRef.current;
      navigate({ pathname: loc.pathname, search: withParam(loc.search, d) }, { replace: true });
    },
    [navigate],
  );

  useEffect(() => {
    const fromUrl = readParam(location.search);
    if (fromUrl !== null && fromUrl !== asOf) {
      setState(fromUrl); // geri/ileri veya paylaşılan link
    } else if (fromUrl === null && asOf !== null) {
      // iç link ile gezinme parametreyi düşürdü → seçili günü URL'ye geri yaz
      navigate({ pathname: location.pathname, search: withParam(location.search, asOf) }, { replace: true });
    }
    // asOf bilerek bağımlılık değil: sadece URL değişimine tepki veriyoruz
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, location.search, navigate]);

  const value = useMemo(() => ({ asOf, setAsOf }), [asOf, setAsOf]);
  return <AsOfCtx.Provider value={value}>{children}</AsOfCtx.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAsOf(): AsOfState {
  const v = useContext(AsOfCtx);
  if (!v) throw new Error("useAsOf must be used inside AsOfProvider");
  return v;
}
