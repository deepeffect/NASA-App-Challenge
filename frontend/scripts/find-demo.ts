/**
 * Demo mürettebatı bulucu: bir görevdeki astronotlardan farklı desenleri temsil eden 5-6 kişi önerir
 * (apps/monitor/config.ts → DEMO_CREW). Durumları Dünya API'sinden okur; ekranın gösterdiğiyle aynıdır.
 *
 *   npm run find-demo                  # varsayılan görev: Mars_Transit
 *   npm run find-demo -- Lunar_Surface
 *
 * Ön koşul: Dünya istasyonu açık (npm run dev:earth). Ortam: FIND_DEMO_API (varsayılan http://127.0.0.1:8001)
 *
 * Kurallar: her desenden (healthy, mild_issue, recovering, acute_episode, getting_worse, chronic_sick) en iyi temsilci;
 * en az biri 30 gün içinde sırayla Normal → Dikkat → Rahatsız geçer. İlk kişi smoke testinde check-in yapan
 * astronottur: bugün Normal ve öneri listesi boş olmayan biri seçilir (smoke, öneriyi işaretleyerek olay üretir).
 */
const API = (process.env.FIND_DEMO_API ?? "http://127.0.0.1:8001").replace(/\/$/, "");
const MISSION = process.argv[2] ?? "Mars_Transit";
const PROFILES = ["healthy", "mild_issue", "recovering", "acute_episode", "getting_worse", "chronic_sick"] as const;

interface Member { astronaut: { id: string; mission: string; profile: string; age: number; sex: string }; status: number; score: number; share: string | null }
interface Cand { id: string; profile: string; statuses: number[]; today: number; score: number; todo: number; transition: number[] | null }

async function get<T>(path: string, token?: string): Promise<T> {
  const r = await fetch(`${API}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return (await r.json()) as T;
}

/** Normal → Dikkat → Rahatsız sırasıyla geçtiği günler (1'den), yoksa null. */
function transition(s: number[]): number[] | null {
  const a = s.indexOf(0);
  if (a < 0) return null;
  const b = s.indexOf(1, a + 1);
  if (b < 0) return null;
  const c = s.indexOf(2, b + 1);
  return c < 0 ? null : [a + 1, b + 1, c + 1];
}

const count = (s: number[], v: number) => s.filter((x) => x === v).length;

/** Desene göre "hikâyeyi en iyi anlatan" puanı (büyük olan iyi). */
function fit(c: Cand): number {
  const s = c.statuses;
  switch (c.profile) {
    case "healthy":
      return count(s, 0) * 10 + (c.today === 0 ? 50 : 0) + (c.todo > 0 ? 100 : 0) + c.score / 100;
    case "mild_issue":
      return count(s, 1) * 10 + (c.today === 1 ? 50 : 0);
    case "recovering":
      return (s[0] === 2 ? 50 : 0) + (c.today === 0 ? 50 : 0) + count(s, 0);
    case "acute_episode":
      return (s[0] === 0 ? 30 : 0) + (c.transition ? 40 : 0) + (c.today >= 1 ? 20 : 0) + count(s, 0);
    case "getting_worse":
      return (c.transition ? 100 : 0) + (c.today === 2 ? 30 : 0) + (c.transition ? 30 - c.transition[0] : 0);
    case "chronic_sick":
      return count(s, 2) * 10 + (c.today === 2 ? 30 : 0);
    default:
      return 0;
  }
}

async function main(): Promise<number> {
  const token = (await (await fetch(`${API}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ id: "EARTH", password: "EARTH" }) })).json()).token as string;
  const crew = (await get<{ astronauts: Member[] }>("/api/monitor/crew?lang=en", token)).astronauts.filter((m) => m.astronaut.mission === MISSION);
  if (!crew.length) {
    console.error(`"${MISSION}" görevinde astronot yok.`);
    return 1;
  }
  const cands: Cand[] = [];
  for (const m of crew) {
    const id = m.astronaut.id;
    const ov = await get<{ today: number; strip: { status: number }[] }>(`/api/monitor/astronauts/${id}?lang=en`, token);
    const day = await get<{ view: { todo: unknown[] } }>(`/api/monitor/astronauts/${id}/days/${ov.today}?lang=en`, token);
    const statuses = ov.strip.map((d) => d.status);
    cands.push({ id, profile: m.astronaut.profile, statuses, today: m.status, score: m.score, todo: day.view.todo.length, transition: transition(statuses) });
  }

  const picks: Cand[] = [];
  for (const p of PROFILES) {
    const best = cands.filter((c) => c.profile === p).sort((a, b) => fit(b) - fit(a) || a.id.localeCompare(b.id))[0];
    if (best) picks.push(best);
  }
  // Geçiş şartı: seçilenlerde yoksa geçişi olan en iyi adayı ekle
  if (!picks.some((c) => c.transition)) {
    const t = cands.filter((c) => c.transition && !picks.includes(c)).sort((a, b) => fit(b) - fit(a))[0];
    if (t) picks.push(t);
  }

  const glyph = (s: number) => (s === 2 ? "◆" : s === 1 ? "▲" : "·");
  console.log(`\nGörev ${MISSION}: ${crew.length} astronot. Desen başına aday sayısı:`);
  console.log(PROFILES.map((p) => `${p} ${cands.filter((c) => c.profile === p).length}`).join(" · "));
  console.log(`\nÖnerilen ekip (· Normal  ▲ Dikkat  ◆ Rahatsız; gün 1 → bugün):\n`);
  for (const c of picks) {
    const tr = c.transition ? `Normal→Dikkat→Rahatsız: gün ${c.transition.join(" → ")}` : "";
    console.log(`  ${c.id}  ${c.profile.padEnd(13)} ${c.statuses.map(glyph).join("")}  skor ${c.score.toFixed(0).padStart(3)}  öneri ${c.todo}  ${tr}`);
  }
  const first = picks[0];
  if (first && (first.today !== 0 || first.todo === 0)) console.log(`\nUyarı: ${first.id} smoke testi için uygun değil (bugün Normal ve önerisi olan biri olmalı).`);
  if (!picks.some((c) => c.transition)) console.log("\nUyarı: Normal → Dikkat → Rahatsız geçişi yapan aday bulunamadı.");
  console.log(`\nDEMO_CREW = [${picks.map((c) => `"${c.id}"`).join(", ")}]\n`);
  return 0;
}

main().then((c) => process.exit(c), (e) => {
  console.error(e instanceof Error ? e.message : e);
  console.error(`Dünya istasyonu açık mı? (${API}) → npm run dev:earth`);
  process.exit(1);
});
