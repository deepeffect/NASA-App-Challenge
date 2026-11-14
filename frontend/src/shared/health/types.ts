/** Ortak sağlık bileşenlerinin tipleri. Veri tipleri API sözleşmesinden gelir (`npm run gen:api`). */
import type { components } from "../../api/types";

type S = components["schemas"];

/** Ekranı kim görüyor: astronotun kendisi (gemi, /me) veya Dünya üssü (/monitor, salt okunur). */
export type Audience = "astronaut" | "earth";

export type DayView = S["DayView"];
export type StripDay = S["StripDay"];
export type ReadingView = S["ReadingView"];
export type AreaScoreView = S["AreaScoreView"];
export type TodoItemView = S["TodoItemView"];
export type CrewInfo = S["CrewInfo"];
export type CatalogDomain = S["CatalogDomain"];
export type CatalogSolution = S["CatalogSolution"];

/** Skor grafiğinin bir günü. `StripDay` bu tipe doğrudan uyar (`daily` yoksa sadece kümülatif çizilir). */
export interface ScorePoint {
  /** 1'den başlar */
  day: number;
  /** Kümülatif sağlık skoru (0–100) */
  score: number;
  /** O günün tek günlük skoru (0–100); yoksa çizilmez */
  daily?: number | null;
}
