const nf = new Map<number, Intl.NumberFormat>();

export function fmtNum(v: number | null | undefined, decimals = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  let f = nf.get(decimals);
  if (!f) {
    f = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 0, maximumFractionDigits: decimals });
    nf.set(decimals, f);
  }
  return f.format(v);
}

const UNIT_LABELS: Record<string, string> = { degC: "°C", h: "sa", min: "dk", score_1_5: "/5" };

export function unitLabel(unit: string): string {
  return UNIT_LABELS[unit] ?? unit;
}

export function fmtValue(v: number | null | undefined, unit: string, decimals = 1): string {
  if (v === null || v === undefined) return "—";
  const u = unitLabel(unit);
  return u === "/5" ? `${fmtNum(v, decimals)}${u}` : `${fmtNum(v, decimals)} ${u}`;
}

const df = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const dfShort = new Intl.DateTimeFormat("tr-TR", { day: "2-digit", month: "2-digit", timeZone: "UTC" });
const dtf = new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" });

/** "2026-11-14" → "14 Kas 2026" (UTC) */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return df.format(new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso));
}

export function fmtDateShort(iso: string): string {
  return dfShort.format(new Date(`${iso.slice(0, 10)}T00:00:00Z`));
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return `${dtf.format(new Date(iso))} UTC`;
}

/** YYYY-MM-DD + n gün */
export function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
