/**
 * Durum işareti: 1 → sarı üçgen (dikkat), 2 → kırmızı baklava (rahatsız), 0 → hiçbir şey (sakin).
 * Süs öğesidir (aria-hidden); anlamı HER ZAMAN yanındaki metin taşır — durum sadece renkle/şekille anlatılmaz.
 */
export function Glyph({ level, small = false }: { level: number | null | undefined; small?: boolean }) {
  if (level !== 1 && level !== 2) return null;
  return <span className={`glyph g${level}${small ? " sm" : ""}`} aria-hidden="true" />;
}
