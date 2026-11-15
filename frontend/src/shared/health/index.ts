/**
 * Astronot (/me) ve Dünya (/monitor) ekranlarının ORTAK sağlık bileşenleri.
 * Görünüm ve davranış için tek doğru kaynak: frontend/reference/personal-artifact.html
 *
 * İki ekran da aynı sözleşmeyi kullanır (`DayView`, `StripDay`, `CrewInfo`, `PersonalCatalog`; src/api/station.ts).
 * Bileşenler hiçbir kuralı yeniden hesaplamaz: durum, skor, gerekçe, aralık ve bayrak metinleri backend'den gelir.
 *
 * Her bileşen `audience: "astronaut" | "earth"` alır:
 *   - astronaut: to-do öğelerinde "Yaptım" düğmesi.
 *   - earth: salt okunur. Astronotun paylaşmadığı ruh hali / stres ölçümleri "Paylaşılmadı" olarak maskelenir,
 *     to-do başlığı "Astronota gösterilen öneriler" olur, maskeli öğelerin sadece sayısı yazılır. Bu metinler ve
 *     `hidden` işaretleri Dünya'nın kendi `DayView`'ından (`MonitorDay.view`) gelir; gizlilik filtresi gemidedir.
 *
 * Kullanım — bütün bileşenler bir `HealthRoot` içinde olmalıdır (tema, yazı tipleri, tek dar kolon):
 *
 *   <HealthRoot>
 *     <StatusCard audience={a} strip={overview.strip} selectedDay={day} onSelectDay={setDay} view={view} />
 *     <TodoCard audience={a} view={view} onToggleDone={markDone} />
 *     <details className="card more">
 *       <summary>…</summary>
 *       <div className="stack">
 *         <WhoRow audience={a} astronaut={overview.astronaut} />
 *         <ScoreChart audience={a} points={overview.strip} selectedDay={day} onSelectDay={setDay} />
 *         <ReadingsTable audience={a} view={view} domains={catalog.domains} />
 *       </div>
 *     </details>
 *     <SelfCareDialog audience={a} open={open} onClose={close} solutions={catalog.solutions} />
 *   </HealthRoot>
 *
 * Dil: sabit etiketler seçili dili hemen izler, veriye bağlı metinler ise isteğin dilinde gelir. Dil değişince
 * veriyi yeniden isteyin (sorgu anahtarına dili ekleyin); yoksa ekran iki dilde karışık görünür.
 *
 * Ekranın kendi kartları için prototipin sınıfları hazırdır (health.css): card, muted, num, top, pick, whoami,
 * infobtn, login, field, primary, err, ground, calm, chips, linkbtn, cilog, msg, cirow, cinotes, share, earthbar,
 * pick2, more, stack.
 *
 * Kural: durum hiçbir yerde sadece renkle anlatılmaz (ikon + metin) — CLAUDE.md.
 */
export { Glyph } from "./Glyph";
export { HealthRoot, type HealthRootProps, type HealthTheme } from "./HealthRoot";
export { ReadingsTable, type ReadingsTableProps } from "./ReadingsTable";
export { SCORE_NORMAL_FROM, SCORE_UNWELL_BELOW, ScoreChart, type ScoreChartProps } from "./ScoreChart";
export { SelfCareDialog, type SelfCareDialogProps } from "./SelfCareDialog";
export { StatusCard, type StatusCardProps } from "./StatusCard";
export { formatNumber, formatPlain, HEALTH_TEXTS, type HealthTexts, useHealthTexts } from "./texts";
export { TodoCard, type TodoCardProps } from "./TodoCard";
export type {
  AreaScoreView,
  Audience,
  CatalogDomain,
  CatalogSolution,
  CrewInfo,
  DayView,
  ReadingView,
  ScorePoint,
  StripDay,
  TodoItemView,
} from "./types";
export { WhoRow, type WhoRowProps } from "./WhoRow";
