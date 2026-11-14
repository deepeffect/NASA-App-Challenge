/**
 * Dünya üssü ekranının (/monitor) smoke testi (Playwright, headless Chromium).
 *
 * Ön koşul: iki istasyon lokal çalışıyor → kökte `npm run dev:ship` (API :8000) ve `npm run dev:earth`
 * (API :8001, web :5174). Çalıştır: `npm run smoke -- earth`.
 *
 * Adımlar:
 *   1. Giriş (EARTH / EARTH), genel görünüm; 1440 ve 1920 px, TR koyu + EN açık ekran görüntüleri
 *   2. Gemide mürettebatın ilk astronotu (config DEMO_CREW[0]) adına check-in tamamlanır ve "Sadece skorlar" ile paylaşılır → Dünya ekranında
 *      gecikme + 2 sn içinde görünmeli; cevap metni hiçbir yerde görünmemeli
 *   3. Paylaşılmamış bir günde ruh hali / stres "Paylaşılmadı" görünmeli: kartta ve astronot detayında (ölçümler
 *      tablosundaki ruh hali / stres ve "Uyku, ruh hali ve stres" alan skoru); check-in panelinde paylaşılan yok
 *   4. Gemi kapatılır → bağlantı uyarısı çıkmalı, son durum görünmeye devam etmeli; gemi açılır →
 *      bağlantı geri gelmeli ve akış kaldığı seq'ten (boşluksuz, tekrarsız) devam etmeli
 *   5. Astronot detayı (ortak bileşenler, audience="earth"): "Sadece skorlar" check-in paneli (konu + işaret, söz
 *      yok), grafikte kümülatif + tek gün çizgisi, önceki/sonraki ve seçili günün korunması; ortak bileşenlerin
 *      bütün hesaplanmış stili .mon dışındakiyle (yani /me'dekiyle) aynı olmalı
 *   6. Mürettebat kartında son etkinlik ve "Aktif" rozeti (4. adımdaki olay); akışta "Sadece mürettebat" filtresi
 *
 * Gemiyi kapatma/açma: :8000'i dinleyen süreç sonlandırılır (dev:ship'teki Vite'a dokunulmaz); gemi testte
 * smoke'un kendi alt sürecinde aynı dev ayarları ve ship.db ile açılır (Dünya backend'i hiç kapanmaz).
 * Test bitince geçici gemi kapatılır ve dev:ship'in izleyicisi tetiklenerek gemi eski yerine döner
 * (backend/app/__init__.py'nin sadece zaman damgası güncellenir; bu dev:earth backend'ini de bir kez yeniden
 * başlatır). İzleyici yoksa (örn. `npm run serve`) gemi kapalı kalır ve rapor söyler; smoke arka planda sunucu bırakmaz.
 *
 * Ayrıca: sayfa gemiye hiç istek atmamalı; konsol hatası, yakalanmamış hata, 4xx/5xx olmamalı;
 * monitor.css'teki her seçici .mon ile başlamalı ve ortak bileşenleri (.ahc) dışlamalı (bkz. monitor.css başı).
 * Ortam değişkenleri: SMOKE_SHIP_API, SMOKE_EARTH_API, SMOKE_EARTH_WEB, SMOKE_ASTRONAUT
 * Not: Bu astronotun bugünkü check-in'i bir kez paylaşılınca geri alınamaz; ölçümü tekrarlamak için önce
 * `npm run reset -- ship` ve `npm run reset -- earth`.
 */
import { type ChildProcess, spawn } from "node:child_process";
import { mkdirSync, openSync, readFileSync, rmSync, utimesSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { type Browser, chromium, type Page } from "playwright";

// Port / süreç yardımcıları ortak modülde (npm run stop da onu kullanır): scripts/ports.mjs
import { killPid, listeningPid } from "../../scripts/ports.mjs";
import { DEMO_CREW, MISSION } from "../src/apps/monitor/config.ts";

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = join(FRONTEND, "..");
const OUT = join(FRONTEND, "screenshots", "earth");
const SHIP = (process.env.SMOKE_SHIP_API ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const EARTH = (process.env.SMOKE_EARTH_API ?? "http://127.0.0.1:8001").replace(/\/$/, "");
const EARTH_WEB_DEFAULT = (process.env.SMOKE_EARTH_WEB ?? "http://localhost:5174").replace(/\/$/, "");
const DEMO_CREW_SIZE = DEMO_CREW.length;
/**
 * Check-in yapan astronot: mürettebatın ilki (bugün Normal, öneri listesi boş değil — npm run find-demo).
 * Paylaşım geri alınamadığı için DB sıfırlamadan yeniden ölçmek isterseniz: SMOKE_ASTRONAUT=<mürettebattan biri>.
 */
const ID = process.env.SMOKE_ASTRONAUT?.trim().toUpperCase() || DEMO_CREW[0];
const isWin = process.platform === "win32";

type IssueKind = "console.error" | "pageerror" | "http" | "requestfailed" | "check" | "ship-request";
interface Issue { kind: IssueKind; text: string }
interface StepResult { name: string; files: string[]; issues: Issue[]; notes: string[]; ms: number }
const c = { red: "\x1b[31m", green: "\x1b[32m", yellow: "\x1b[33m", dim: "\x1b[2m", bold: "\x1b[1m", off: "\x1b[0m" };

// ----------------------------------------------------------------------------- yardımcılar
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function reachable(url: string): Promise<boolean> {
  try {
    return (await fetch(url, { signal: AbortSignal.timeout(3000) })).ok;
  } catch {
    return false;
  }
}

async function waitUntil(fn: () => Promise<boolean>, timeoutMs: number, every = 400): Promise<boolean> {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    if (await fn()) return true;
    await sleep(every);
  }
  return false;
}

async function api<T>(base: string, method: string, path: string, token?: string, body?: unknown): Promise<T> {
  const sep = path.includes("?") ? "&" : "?";
  const res = await fetch(`${base}${path}${sep}lang=tr`, {
    method,
    headers: { "content-type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`${method} ${base}${path} → ${res.status} ${text.slice(0, 200)}`);
  return JSON.parse(text) as T;
}

const login = async (base: string, id: string) => (await api<{ token: string }>(base, "POST", "/api/auth/login", undefined, { id, password: id })).token;

interface LinkStatus { connected: boolean; last_seq: number; delay_seconds: number | null; epoch: string | null }
interface CheckinState { done: boolean; share: string | null; can_reset: boolean; editable: boolean; options: string[] }

const SHIP_PORT = new URL(SHIP).port || "8000";
const VENV_PY = isWin ? join(ROOT, "backend", ".venv", "Scripts", "python.exe") : join(ROOT, "backend", ".venv", "bin", "python");
/** `npm run dev:ship` ile aynı backend ortamı (scripts/station.mjs → devBackendEnv("ship")). */
const shipEnv = () => ({
  ...process.env,
  PYTHONIOENCODING: "utf-8",
  PYTHONUTF8: "1",
  STATION_ROLE: "ship",
  DATA_SOURCE: "astronaut_health",
  DATABASE_URL: `sqlite:///${join(ROOT, "data", "processed", "ship.db").replaceAll("\\", "/")}`,
  CORS_ORIGINS: "http://localhost:5173,http://127.0.0.1:5173",
  EARTH_LINK_TOKEN: process.env.EARTH_LINK_TOKEN ?? "dev-link-token",
});

/**
 * Test sırasında gemiyi aç: smoke'un kendi alt süreci (dev:ship ile aynı ayar ve ship.db). Dünya backend'i
 * bu sırada çalışmaya devam eder; böylece "Dünya açıkken gemi geri gelir" senaryosu olduğu gibi denenir.
 */
function startTempShip(): ChildProcess {
  return spawn(VENV_PY, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", SHIP_PORT], {
    cwd: join(ROOT, "backend"),
    stdio: ["ignore", openSync(join(OUT, "ship-temp.log"), "a"), openSync(join(OUT, "ship-temp.log"), "a")],
    env: shipEnv(),
  });
}

/**
 * Test bitince ortamı eski haline getir: geçici gemiyi kapat, dev:ship'in backend-dev.mjs izleyicisini tetikle
 * (backend/app/__init__.py'nin sadece zaman damgası; içerik değişmez). Not: aynı klasörü izleyen dev:earth
 * backend'i de bu sırada yeniden başlar (veri earth.db'de kalır, alıcı kaldığı seq'ten devam eder).
 * İzleyici yoksa (örn. `npm run serve`) gemi kapalı kalır ve rapor bunu söyler: smoke arka planda sunucu bırakmaz.
 */
async function restoreShip(temp: ChildProcess | null, notes: string[]): Promise<void> {
  if (temp && temp.exitCode === null && temp.pid) {
    killPid(temp.pid);
    await waitUntil(async () => !(await reachable(`${SHIP}/api/station`)), 10_000, 200);
  }
  const now = new Date();
  utimesSync(join(ROOT, "backend", "app", "__init__.py"), now, now);
  if (await waitUntil(() => reachable(`${SHIP}/api/station`), 20_000)) {
    notes.push("gemi dev:ship penceresinde yeniden açıldı (izleyici)");
    return;
  }
  notes.push(`${c.yellow}gemi kendi penceresinde yeniden açılmadı (izleyici yok veya çalışmıyor): npm run dev:ship ile başlatın${c.off}`);
}

/**
 * Ortak bileşenlerin (.ahc) Dünya'da /me'dekiyle aynı stilde olduğunu denetler: detaydaki .ahc ağacı .mon'un
 * dışına (body'ye, aynı genişlikte) kopyalanır ve her öğenin BÜTÜN hesaplanmış stili karşılaştırılır. Fark varsa
 * monitor.css (veya .mon'dan miras) ortak bileşenlere sızıyor demektir. Denetimin kör olmadığını göstermek için
 * sonra bilerek sızan bir kural eklenir: o zaman fark çıkmalı. Yerleşim bağlamından gelen iki fark türü sayılmaz
 * (kökün flex öğesi olması, mutlak konumlu öğenin sayfadaki yeri); gerisi, her özellik, birebir aynı olmalı.
 */
async function sharedStyleDiffs(page: Page): Promise<{ elements: number; diffs: string[]; control: number }> {
  await page.mouse.move(1, 1);
  // Şerit çubukları açılışta CSS geçişiyle uzar; kopyada geçiş olmaz → önce .ahc içindeki animasyonlar bitsin
  await page.waitForFunction(
    `document.getAnimations().every((a) => a.playState !== "running" || !a.effect?.target?.closest?.(".ahc"))`,
    null,
    { timeout: 5000 },
  );
  // Düz JS metni: tsx (esbuild) adlandırılmış fonksiyonlara tarayıcıda olmayan __name() ekler
  return page.evaluate(`(() => {
    document.activeElement?.blur();
    const orig = document.querySelector(".mon .ahc");
    if (!orig) throw new Error(".mon içinde .ahc yok");
    const host = document.createElement("div");
    host.style.cssText = "position:absolute;left:0;top:0;width:" + orig.getBoundingClientRect().width + "px";
    const clone = orig.cloneNode(true);
    host.append(clone);
    document.body.append(host);
    const leak = document.createElement("style");
    try {
      const A = [orig, ...orig.querySelectorAll("*")];
      const B = [clone, ...clone.querySelectorAll("*")];
      // <select>'in seçili değeri özellikte durur, kopyalanmaz
      A.forEach((el, i) => { if (el instanceof HTMLSelectElement) B[i].value = el.value; });
      const label = (el) => el.tagName.toLowerCase() + (el.classList.length ? "." + [...el.classList].join(".") : "");
      // Stil değil yerleşim bağlamı (ikisi de sızma değildir):
      //  - kök .ahc Dünya'da .mon-main'in flex öğesi, kopyada düz blok: min-* "auto" / "0px"
      //  - mutlak/sabit konumlu öğenin top/left/inset… değeri sayfadaki yerine göre hesaplanır
      const MIN = /^min-(width|height|inline-size|block-size)$/;
      const INSET = /^(top|right|bottom|left|inset(-.+)?)$/;
      const compare = (limit) => {
        const out = [];
        for (let i = 0; i < A.length && out.length < limit; i++) {
          const a = getComputedStyle(A[i]);
          const b = getComputedStyle(B[i]);
          const positioned = /^(absolute|fixed)$/.test(a.position) && a.position === b.position;
          for (let k = 0; k < a.length; k++) {
            const p = a[k];
            // Özel değişkenler (--x) .mon'dan miras gelir ama ortak bileşenler kullanmaz; etkileri gerçek özelliklerde görünür
            if (p.startsWith("--")) continue;
            const va = a.getPropertyValue(p), vb = b.getPropertyValue(p);
            if (va === vb) continue;
            if (i === 0 && MIN.test(p) && (va === "auto" || vb === "auto")) continue;
            if (positioned && INSET.test(p)) continue;
            out.push(label(A[i]) + " " + p + ": " + va + " ≠ " + vb);
          }
        }
        return out;
      };
      const diffs = compare(20);
      leak.textContent = ".mon .card { padding-top: 1px; } .mon .glyph { width: 21px; }";
      document.head.append(leak);
      const control = compare(5).length;
      return { elements: A.length, diffs, control };
    } finally {
      leak.remove();
      host.remove();
    }
  })()`);
}

function instrument(page: Page, report: (i: Issue) => void): void {
  const shipOrigin = new URL(SHIP).origin;
  page.on("console", (m) => {
    if (m.type() === "error") report({ kind: "console.error", text: m.text() });
  });
  page.on("pageerror", (e) => report({ kind: "pageerror", text: e.message }));
  page.on("request", (r) => {
    if (r.url().startsWith(shipOrigin)) report({ kind: "ship-request", text: `Dünya ekranı gemiye istek attı: ${r.method()} ${r.url()}` });
  });
  page.on("requestfailed", (r) => {
    const err = r.failure()?.errorText ?? "";
    if (!err.includes("ERR_ABORTED")) report({ kind: "requestfailed", text: `${r.method()} ${r.url()} — ${err}` });
  });
  page.on("response", (r) => {
    if (r.status() >= 400) report({ kind: "http", text: `${r.status()} ${r.request().method()} ${r.url()}` });
  });
}

async function loginEarth(page: Page, web: string): Promise<void> {
  await page.goto(`${web}/monitor`);
  await page.locator("#mon-id").fill("EARTH");
  await page.locator("#mon-pw").fill("EARTH");
  await page.getByRole("button", { name: "Giriş yap" }).click();
  await page.locator("article[data-astronaut]").nth(DEMO_CREW_SIZE - 1).waitFor({ timeout: 15_000 });
  await page.locator("article[data-astronaut] .spark svg").first().waitFor({ timeout: 15_000 });
  await page.locator("[data-area]").first().waitFor({ timeout: 15_000 });
}

/** Görevin adı backend kataloğundan (CrewInfo.mission_label), verilen dilde: ekranlar bu adı göstermeli. */
async function missionLabel(token: string, lang: "tr" | "en"): Promise<string> {
  const res = await fetch(`${EARTH}/api/monitor/crew?lang=${lang}`, { headers: { Authorization: `Bearer ${token}`, "Accept-Language": lang } });
  if (!res.ok) throw new Error(`GET /api/monitor/crew?lang=${lang} → ${res.status}`);
  const crew = (await res.json()) as { astronauts: { astronaut: { mission: string; mission_label: string } }[] };
  const m = crew.astronauts.find((x) => x.astronaut.mission === MISSION.id);
  if (!m) throw new Error(`${MISSION.id} görevinde astronot yok`);
  return m.astronaut.mission_label;
}

/** Detay adresi mi: /monitor/astronaut/<id> ve (verildiyse) ?day=<gün>; gün verilmezse ?day olmamalı. */
const atDetail = (id: string, day?: number) => (u: URL) =>
  u.pathname.endsWith(`/monitor/astronaut/${id}`) && (day === undefined ? !u.searchParams.has("day") : u.searchParams.get("day") === String(day));

async function check(issues: Issue[], what: string, fn: () => Promise<unknown>): Promise<boolean> {
  try {
    await fn();
    return true;
  } catch (e) {
    issues.push({ kind: "check", text: `${what}: ${(e as Error).message.split("\n")[0]}` });
    return false;
  }
}

/** Ortak bileşenlerin kökü (HealthRoot) ve altı: monitor.css'in hiçbir kuralı buraya uygulanmamalı. */
const AHC_EXCLUDE = ":not(:where(.ahc, .ahc *))";

/**
 * monitor.css'te kapsam kuralına uymayan seçiciler ve mon- öneksiz @keyframes adları:
 *   - `.mon` ile başlamalı (App bu dosyayı her rotada yükler; kapsamsız seçici /me'deki ortak bileşenlere sızar)
 *   - öznesi AHC_EXCLUDE ile bitmeli, sözde öğeden önce (astronot detayındaki ortak bileşenler .mon'un içinde)
 */
function unscopedMonitorSelectors(): string[] {
  const css = readFileSync(join(FRONTEND, "src", "apps", "monitor", "monitor.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const bad: string[] = [];
  const inKeyframes: boolean[] = []; // açık her blok için: @keyframes içinde mi
  let prelude = "";
  for (const ch of css) {
    if (ch === "{") {
      const p = prelude.trim();
      const parentKf = inKeyframes.at(-1) ?? false;
      if (p.startsWith("@")) {
        if (/^@keyframes\s+(?!mon-)/.test(p)) bad.push(p);
        inKeyframes.push(p.startsWith("@keyframes"));
      } else {
        if (!parentKf)
          bad.push(
            ...p
              .split(/,(?![^(]*\))/) // :where(.ahc, .ahc *) içindeki virgülde bölme
              .map((s) => s.trim())
              .filter((s) => !/^\.mon(?![\w-])/.test(s) || !s.replace(/::[\w-]+$/, "").endsWith(AHC_EXCLUDE)),
          );
        inKeyframes.push(parentKf);
      }
      prelude = "";
    } else if (ch === "}") {
      inKeyframes.pop();
      prelude = "";
    } else if (ch === ";") prelude = "";
    else prelude += ch;
  }
  return bad;
}

// ----------------------------------------------------------------------------- ana akış
export async function runEarthSmoke(): Promise<number> {
  const [shipSt, earthSt] = await Promise.all(
    [SHIP, EARTH].map(async (b) => {
      try {
        return (await (await fetch(`${b}/api/station`, { signal: AbortSignal.timeout(3000) })).json()) as { role: string; legacy_enabled: boolean };
      } catch {
        return null;
      }
    }),
  );
  if (shipSt?.role !== "ship" || shipSt.legacy_enabled || earthSt?.role !== "earth") {
    console.error(`${c.red}Gemi (${SHIP}) ve Dünya (${EARTH}) istasyonları açık değil. Önce kökte: npm run dev:ship ve npm run dev:earth${c.off}`);
    return 2;
  }
  if (!DEMO_CREW.includes(ID)) {
    console.error(`${c.red}SMOKE_ASTRONAUT=${ID} mürettebatta yok (DEMO_CREW: ${DEMO_CREW.join(", ")}).${c.off}`);
    return 2;
  }
  const web = (await reachable(`${EARTH_WEB_DEFAULT}/monitor`)) ? EARTH_WEB_DEFAULT : EARTH;
  const earthToken = await login(EARTH, "EARTH");
  const linkOf = () => api<LinkStatus>(EARTH, "GET", "/api/link/status", earthToken);
  if (!(await waitUntil(async () => (await linkOf()).connected, 20_000))) {
    console.error(`${c.red}Dünya gemiye bağlı değil (/api/link/status connected=false). SHIP_URL ve EARTH_LINK_TOKEN'ı kontrol edin.${c.off}`);
    return 2;
  }

  rmSync(OUT, { recursive: true, force: true });
  mkdirSync(OUT, { recursive: true });
  const marker = `SMOKE-${Date.now().toString(36).toUpperCase()}`;
  const results: StepResult[] = [];
  const restoreNotes: string[] = [];
  let browser: Browser | null = null;
  let tempShip: ChildProcess | null = null;
  let shipKilled = false;

  try {
    browser = await chromium.launch();
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "tr-TR", colorScheme: "dark" });
    await context.addInitScript(() => {
      try {
        localStorage.setItem("ahm-lang", "tr");
      } catch {
        /* yok say */
      }
    });
    const page = await context.newPage();
    let current: StepResult = { name: "", files: [], issues: [], notes: [], ms: 0 };
    instrument(page, (i) => current.issues.push(i));
    const shot = async (file: string, opts: { selector?: string; full?: boolean } = {}) => {
      const path = join(OUT, file);
      if (opts.selector) await page.locator(opts.selector).first().screenshot({ path });
      else await page.screenshot({ path, fullPage: !!opts.full });
      current.files.push(`earth/${file}`);
    };
    const step = async (name: string, run: () => Promise<void>) => {
      current = { name, files: [], issues: [], notes: [], ms: 0 };
      const t0 = Date.now();
      try {
        await run();
      } catch (e) {
        current.issues.push({ kind: "check", text: `adım başarısız: ${(e as Error).message.split("\n")[0]}` });
        await page.screenshot({ path: join(OUT, `FAIL-${results.length + 1}.png`), fullPage: true }).catch(() => undefined);
      }
      current.ms = Date.now() - t0;
      results.push(current);
    };

    // ------------------------------------------------------------------ 1
    await step("1. Giriş ve genel görünüm (1440 / 1920, TR koyu, EN açık)", async () => {
      await check(current.issues, "monitor.css: her seçici .mon altında ve ortak bileşenlerin (.ahc) dışında", async () => {
        const bad = unscopedMonitorSelectors();
        if (bad.length) throw new Error(`kapsamsız: ${bad.slice(0, 8).join(" | ")}${bad.length > 8 ? ` … (+${bad.length - 8})` : ""}`);
      });
      await loginEarth(page, web);
      await page.locator('.linkbar[data-link="up"]').waitFor({ timeout: 10_000 });
      await check(current.issues, "bağlantı çubuğu metni", () => page.getByText(/Gemi bağlantısı:/).first().waitFor({ timeout: 5000 }));
      await check(current.issues, "son temas", () => page.getByText(/son temas/).first().waitFor({ timeout: 5000 }));
      await check(current.issues, "kuyruk", () => page.getByText(/kuyrukta \d+ olay/).first().waitFor({ timeout: 5000 }));
      await check(current.issues, "ışık gecikmesi etiketi", () => page.getByText(/Işık gecikmesi \(simüle\)/).first().waitFor({ timeout: 5000 }));
      const missionTr = await missionLabel(earthToken, "tr");
      await check(current.issues, `görev çubuğu: backend kataloğundaki ad (${missionTr})`, async () => {
        const bar = page.locator(`[data-mission="${MISSION.id}"]`);
        await bar.locator("b").getByText(missionTr, { exact: true }).waitFor({ timeout: 5000 });
        const txt = await bar.innerText();
        if (!txt.includes(`${DEMO_CREW_SIZE} kişilik mürettebat`)) throw new Error(`görev çubuğu: ${txt}`);
      });
      await check(current.issues, "tablodaki görev adı görev çubuğuyla aynı", async () => {
        const cell = (await page.locator(`tr[data-astronaut="${DEMO_CREW[0]}"] td`).nth(1).innerText()).trim();
        if (cell !== missionTr) throw new Error(`tablo "${cell}", görev çubuğu "${missionTr}"`);
      });
      await check(current.issues, `mürettebatın hepsi ${MISSION.id}`, async () => {
        const crew = await api<{ astronauts: { astronaut: { id: string; mission: string } }[] }>(EARTH, "GET", "/api/monitor/crew", earthToken);
        const other = crew.astronauts.filter((m) => DEMO_CREW.includes(m.astronaut.id) && m.astronaut.mission !== MISSION.id).map((m) => m.astronaut.id);
        if (other.length) throw new Error(`başka görevde: ${other.join(", ")}`);
      });
      await check(current.issues, "footer", () => page.getByText("NASA Space Apps Challenge 2026 için AI Gambit tarafından geliştirildi").waitFor({ timeout: 5000 }));
      await check(current.issues, "tüm astronotlar tablosu (200)", () => page.getByText(/200 \/ 200 astronot/).waitFor({ timeout: 10_000 }));
      await page.waitForTimeout(500);
      await shot("01-overview-1440.png");
      await shot("01b-overview-1440-full.png", { full: true });
      await page.setViewportSize({ width: 1920, height: 1080 });
      await page.waitForTimeout(600);
      await shot("01c-overview-1920.png");
      // EN + açık tema
      await page.getByRole("button", { name: "EN", exact: true }).click();
      await page.getByRole("button", { name: "Açık tema" }).or(page.getByRole("button", { name: "Light theme" })).click();
      await check(current.issues, "EN metinleri", () => page.getByText("All astronauts").waitFor({ timeout: 10_000 }));
      const missionEn = await missionLabel(earthToken, "en");
      await check(current.issues, `görev çubuğu EN: ${missionEn}`, () =>
        page.locator(`[data-mission="${MISSION.id}"] b`).getByText(missionEn, { exact: true }).waitFor({ timeout: 10_000 }),
      );
      await page.waitForTimeout(600);
      await shot("01d-overview-1920-en-light.png");
      await page.getByRole("button", { name: "Dark theme" }).click();
      await page.getByRole("button", { name: "TR", exact: true }).click();
      await page.getByText("Tüm astronotlar").waitFor({ timeout: 10_000 });
      await page.setViewportSize({ width: 1440, height: 900 });
    });

    // ------------------------------------------------------------------ 2
    await step(`2. ${ID} check-in + 'Sadece skorlar' → Dünya'da gecikme + 2 sn içinde, cevap metni yok`, async () => {
      const shipToken = await login(SHIP, ID);
      let st = await api<CheckinState>(SHIP, "GET", "/api/checkin", shipToken);
      if (st.done && st.share === "full") throw new Error(`${ID} bugünkü check-in'i 'Her şey' ile paylaşmış; temiz deneme için: npm run reset -- ship && npm run reset -- earth`);
      const alreadyShared = st.done && st.share === "scores";
      if (alreadyShared) {
        current.notes.push(`${ID} bugün zaten 'Sadece skorlar' ile paylaşmış (önceki çalıştırma); süre ölçülemedi, sadece görünürlük denetlendi. Yeniden ölçmek için: npm run reset -- ship && npm run reset -- earth`);
      } else {
        if (st.done && st.can_reset) st = await api<CheckinState>(SHIP, "POST", "/api/checkin/reset", shipToken);
        const answers = [`Kötü uyudum ${marker}`, `Biraz düşük ${marker}`, `Biraz ${marker}`, "Yok", "Hayır"];
        for (let i = 0; i < 8 && !st.done; i++) {
          const r = await api<{ checkin: CheckinState }>(SHIP, "POST", "/api/checkin/turn", shipToken, { answer: answers[Math.min(i, answers.length - 1)] });
          st = r.checkin;
        }
        if (!st.done) throw new Error("check-in tamamlanamadı");
        await check(current.issues, "tamamlanınca kartta 'Gizli tuttu'", () =>
          page.locator(`article[data-astronaut="${ID}"] [data-share="private"]`).waitFor({ timeout: 5000 }),
        );
        const delay = (await linkOf()).delay_seconds ?? 0;
        const budget = delay * 1000 + 2000;
        const t0 = Date.now();
        await api(SHIP, "POST", "/api/checkin/share", shipToken, { level: "scores" });
        const card = page.locator(`article[data-astronaut="${ID}"] [data-share="scores"]`);
        const feedItem = page.locator(`li[data-type="checkin.shared"][data-astronaut="${ID}"]`).first();
        try {
          await Promise.all([card.waitFor({ timeout: budget }), feedItem.waitFor({ timeout: budget })]);
          current.notes.push(`paylaşım Dünya ekranında ${Date.now() - t0} ms'de göründü (bütçe: gecikme ${delay} sn + 2 sn)`);
        } catch {
          current.issues.push({ kind: "check", text: `paylaşım ${budget} ms içinde Dünya ekranında görünmedi` });
        }
        await page.waitForTimeout(250);
        await shot("02-shared.png");
        await shot("02b-checkin-card.png", { selector: `article[data-astronaut="${ID}"]` });
      }
      await check(current.issues, "kartta 'Sadece skorlar'", () => page.locator(`article[data-astronaut="${ID}"]`).getByText("Sadece skorlar").waitFor({ timeout: 5000 }));
      await check(current.issues, "akışta 'Check-in paylaşıldı: Sadece skorlar'", () =>
        page.locator(`li[data-type="checkin.shared"][data-astronaut="${ID}"]`).getByText("Check-in paylaşıldı: Sadece skorlar").first().waitFor({ timeout: 5000 }),
      );
      await check(current.issues, "paylaşılınca ruh hali / stres değerleri görünür", () =>
        page.locator(`article[data-astronaut="${ID}"] [data-private="shared"]`).waitFor({ timeout: 5000 }),
      );
      // cevap metni hiçbir yerde olmamalı: sayfa (öznitelikler dahil) ve Dünya API'si
      const html = await page.content();
      if (/SMOKE-[0-9A-Z]+/.test(html) || /Kötü uyudum/.test(html)) current.issues.push({ kind: "check", text: "check-in cevap metni Dünya ekranında görünüyor" });
      const day = await api<unknown>(EARTH, "GET", `/api/monitor/astronauts/${ID}/days/30`, earthToken);
      if (/SMOKE-|Kötü uyudum/.test(JSON.stringify(day))) current.issues.push({ kind: "check", text: "check-in cevap metni Dünya API'sinde var" });
    });

    // ------------------------------------------------------------------ 3
    await step("3. Paylaşılmamış günde ruh hali / stres 'Paylaşılmadı'", async () => {
      const crew = await api<{ astronauts: { astronaut: { id: string }; share: string | null }[] }>(EARTH, "GET", "/api/monitor/crew", earthToken);
      const shareOf = new Map(crew.astronauts.map((m) => [m.astronaut.id, m.share]));
      const ids = await page.locator("article[data-astronaut]").evaluateAll((els) => els.map((e) => e.getAttribute("data-astronaut") ?? ""));
      const target = ids.find((id) => !["scores", "full"].includes(shareOf.get(id) ?? ""));
      if (!target) throw new Error("mürettebatta paylaşılmamış günü olan astronot yok");
      const row = page.locator(`article[data-astronaut="${target}"] [data-private="hidden"]`);
      await check(current.issues, `${target} kartında 'Ruh hali · Stres: Paylaşılmadı'`, async () => {
        await row.waitFor({ timeout: 5000 });
        const txt = await row.innerText();
        if (!/Ruh hali/.test(txt) || !/Stres/.test(txt) || !/Paylaşılmadı/.test(txt)) throw new Error(`satır metni: ${txt}`);
      });
      await check(current.issues, `${target} davranış alanı kilitli ve açıklamalı`, async () => {
        const txt = await page.locator(`article[data-astronaut="${target}"] [data-area="behavioral"]`).innerText();
        if (!/paylaşılmadı/i.test(txt)) throw new Error(`alan metni: ${txt}`);
      });
      const day = await api<{ view: { readings: { col: string; value_text: string; hidden: boolean }[] } }>(
        EARTH, "GET", `/api/monitor/astronauts/${target}/days/30`, earthToken,
      );
      for (const col of ["beh_mood_score", "beh_stress_score"]) {
        const r = day.view.readings.find((x) => x.col === col);
        if (!r?.hidden || r.value_text !== "Paylaşılmadı") current.issues.push({ kind: "check", text: `${target} ${col}: Dünya API'sinde gizli değil` });
      }
      await shot("03-not-shared-card.png", { selector: `article[data-astronaut="${target}"]` });

      // Astronot detayı (ortak bileşenler, audience="earth"): kartın kimlik bağlantısından
      await page.locator(`article[data-astronaut="${target}"] a.ccard-id`).click();
      await page.waitForURL(atDetail(target), { timeout: 5000 });
      const table = page.locator(".ahc table.readings");
      await table.waitFor({ timeout: 10_000 });
      for (const [col, label] of [["beh_mood_score", "ruh hali"], ["beh_stress_score", "stres"]]) {
        await check(current.issues, `${target} detay: ${label} ölçümü 'Paylaşılmadı'`, async () => {
          const value = (await table.locator(`tr[data-col="${col}"] td.r`).innerText()).trim();
          if (value !== "Paylaşılmadı") throw new Error(`değer: ${value}`);
        });
      }
      await check(current.issues, `${target} detay: 'Uyku, ruh hali ve stres' alan skoru 'Paylaşılmadı'`, async () => {
        const row = table.locator("tr").filter({ has: page.locator("td.name", { hasText: /^Uyku, ruh hali ve stres$/ }) });
        const value = (await row.locator("td.r").innerText()).trim();
        if (value !== "Paylaşılmadı") throw new Error(`değer: ${value}`);
      });
      await check(current.issues, `${target} detay: check-in panelinde paylaşılan bir şey yok`, async () => {
        const panel = page.locator(".ahc section[data-share]");
        const share = await panel.getAttribute("data-share", { timeout: 5000 });
        if (share !== "none" && share !== "private") throw new Error(`paylaşım: ${share}`);
        if (await panel.locator(".cinotes").count()) throw new Error("konu notları görünüyor");
      });
      await page.waitForTimeout(300);
      await shot("03b-detail-not-shared.png", { full: true });
      await page.locator(".ahc a.linkbtn").click(); // genel görünüme dön
      await page.locator("article[data-astronaut] .spark svg").nth(DEMO_CREW_SIZE - 1).waitFor({ timeout: 10_000 });
      current.notes.push(`${target}: kart, Dünya API'si ve detaydaki ölçümler tablosu denetlendi`);
    });

    // ------------------------------------------------------------------ 4
    await step("4. Gemi kapanınca uyarı + son durum; açılınca akış kaldığı yerden", async () => {
      const port = Number(new URL(SHIP).port || 8000);
      const before = await linkOf();
      const pid = listeningPid(port);
      if (!pid) throw new Error(`:${port} portunu dinleyen gemi süreci bulunamadı`);
      killPid(pid);
      shipKilled = true;
      current.notes.push(`gemi kapatıldı (PID ${pid}; dev:ship'teki Vite'a dokunulmadı)`);
      await check(current.issues, "bağlantı uyarısı", async () => {
        await page.locator(".linkdown").getByText(/Bağlantı yok, son bilinen durum: \d{2}:\d{2}/).waitFor({ timeout: 20_000 });
      });
      await check(current.issues, "uyarıda son durum devam ediyor: kartlar", async () => {
        if ((await page.locator("article[data-astronaut] .spark svg").count()) !== DEMO_CREW_SIZE) throw new Error("kartlar kayboldu");
      });
      await check(current.issues, `uyarıda son durum devam ediyor: ${ID} paylaşımı`, () =>
        page.locator(`article[data-astronaut="${ID}"]`).getByText("Sadece skorlar").waitFor({ timeout: 3000 }),
      );
      await check(current.issues, "uyarıda son durum devam ediyor: tablo ve akış", async () => {
        await page.getByText(/200 \/ 200 astronot/).waitFor({ timeout: 3000 });
        if (!(await page.locator("li[data-seq]").count())) throw new Error("akış boş");
      });
      await check(current.issues, "akışta 'bağlantı koptu' işareti", () => page.locator('li[data-marker="down"]').first().waitFor({ timeout: 5000 }));
      await shot("04-link-down.png");

      tempShip = startTempShip();
      if (!(await waitUntil(() => reachable(`${SHIP}/api/station`), 40_000))) throw new Error("gemi yeniden açılamadı (log: screenshots/earth/ship-temp.log)");
      current.notes.push(`gemi yeniden açıldı (smoke'un geçici gemi süreci, PID ${tempShip.pid}; Dünya backend'i hiç kapanmadı)`);
      await check(current.issues, "bağlantı geri geldi", async () => {
        await page.locator('.linkbar[data-link="up"]').waitFor({ timeout: 60_000 });
        await page.locator(".linkdown").waitFor({ state: "detached", timeout: 5000 });
      });
      await check(current.issues, "akışta 'bağlantı geri geldi' işareti", () => page.locator('li[data-marker="up"]').first().waitFor({ timeout: 5000 }));

      // Yeni olay: astronotun bugünkü ilk önerisini işaretle / kaldır (her çalıştırmada bir olay üretir)
      const shipToken = await login(SHIP, ID);
      const me = await api<{ today: number }>(SHIP, "GET", "/api/me", shipToken);
      const dayView = await api<{ todo: { code: string; done: boolean }[] }>(SHIP, "GET", `/api/me/days/${me.today}`, shipToken);
      const item = dayView.todo[0];
      if (!item) throw new Error(`${ID} için bugün öneri yok; yeni olay üretilemedi (npm run find-demo ile uygun bir ilk kişi seçin)`);
      const lastSeq = (await linkOf()).last_seq;
      if (lastSeq !== before.last_seq) current.issues.push({ kind: "check", text: `kopma sırasında seq değişti (${before.last_seq} → ${lastSeq})` });
      await api(SHIP, "POST", "/api/actions/done", shipToken, { code: item.code, done: !item.done });
      const next = lastSeq + 1;
      await check(current.issues, `akış seq ${next} ile devam ediyor`, () => page.locator(`li[data-seq="${next}"]`).waitFor({ timeout: 10_000 }));
      const evs = await api<{ events: { seq: number }[] }>(EARTH, "GET", "/api/monitor/events?limit=500", earthToken);
      const seqs = evs.events.map((e) => e.seq).sort((a, b) => a - b);
      const gaps = seqs.filter((s, i) => i > 0 && s !== seqs[i - 1] + 1);
      if (seqs[seqs.length - 1] !== next) current.issues.push({ kind: "check", text: `Dünya'daki son seq ${seqs[seqs.length - 1]}, beklenen ${next}` });
      if (gaps.length || new Set(seqs).size !== seqs.length) current.issues.push({ kind: "check", text: `olay listesinde boşluk/tekrar: ${seqs.join(",")}` });
      current.notes.push(`kopmadan önce son seq ${lastSeq}, sonra ${next} (boşluk ve tekrar yok)`);
      await page.waitForTimeout(300);
      await shot("05-resumed.png");
    });

    // ------------------------------------------------------------------ 5
    await step(`5. Astronot detayı (${ID}): ortak bileşenler, paylaşıma göre check-in, iki çizgi, önceki/sonraki`, async () => {
      // Kartın boş bir yerine tıklama da detayı açar
      await page.locator(`article[data-astronaut="${ID}"] .ccard-foot`).click();
      await page.waitForURL(atDetail(ID), { timeout: 5000 });
      await page.locator(".ahc table.readings").waitFor({ timeout: 10_000 });
      await page.locator(".ahc .chart svg").waitFor({ timeout: 10_000 });
      await check(current.issues, "ortak bileşenler audience=earth", async () => {
        for (const sel of ["section.status", "section.todo", "div.who", ".chart", "table.readings"]) {
          const n = await page.locator(`.ahc ${sel}`).count();
          if (!n) throw new Error(`${sel} yok`);
        }
        const aud = await page.locator(".ahc [data-audience]").evaluateAll((els) => [...new Set(els.map((e) => e.getAttribute("data-audience")))]);
        if (aud.length !== 1 || aud[0] !== "earth") throw new Error(`audience: ${aud.join(",")}`);
      });
      await check(current.issues, "detaydaki görev adı görev çubuğuyla aynı", async () => {
        const bar = (await page.locator(`[data-mission="${MISSION.id}"] b`).innerText()).trim();
        const who = await page.locator(".ahc .who").innerText();
        if (!bar || bar === "…" || !who.includes(bar)) throw new Error(`görev çubuğu "${bar}", kimlik satırı "${who}"`);
      });
      await check(current.issues, "check-in paneli 'Sadece skorlar': konular + işaret, astronotun sözleri yok", async () => {
        const panel = page.locator('.ahc section[data-share="scores"]');
        await panel.waitFor({ timeout: 5000 });
        const notes = await panel.locator(".cinotes > div").allInnerTexts();
        if (!notes.length) throw new Error("konu notu yok");
        const bad = notes.filter((n) => !/İşaretlendi|İşaret yok/.test(n));
        if (bad.length) throw new Error(`işaret metni olmayan not: ${bad.join(" | ")}`);
      });
      await check(current.issues, "paylaşılan günde ruh hali / stres değerleri görünür", async () => {
        for (const col of ["beh_mood_score", "beh_stress_score"]) {
          const value = (await page.locator(`.ahc tr[data-col="${col}"] td.r`).innerText()).trim();
          if (!value || value === "Paylaşılmadı") throw new Error(`${col}: ${value}`);
        }
      });
      const html = await page.content();
      if (/SMOKE-[0-9A-Z]+/.test(html) || /Kötü uyudum/.test(html)) current.issues.push({ kind: "check", text: "detayda check-in cevap metni görünüyor" });
      await check(current.issues, "grafikte iki çizgi: kümülatif + tek gün", async () => {
        const cum = await page.locator('.ahc .chart svg path[stroke="var(--series-cum)"]').count();
        const day = await page.locator('.ahc .chart svg path[stroke="var(--series-day)"]').count();
        if (cum !== 1 || day !== 1) throw new Error(`kümülatif ${cum}, tek gün ${day}`);
        const legend = await page.locator(".ahc .legend").innerText();
        if (!/Kümülatif/.test(legend) || !/Tek gün/.test(legend)) throw new Error(`açıklama: ${legend}`);
      });
      await check(current.issues, "ortak bileşenler /me ile aynı stil (monitor.css sızmıyor)", async () => {
        const r = await sharedStyleDiffs(page);
        if (r.diffs.length) throw new Error(`${r.diffs.length}+ fark: ${r.diffs.slice(0, 4).join(" | ")}`);
        if (!r.control) throw new Error("denetim kör: bilerek sızan kural fark üretmedi");
        current.notes.push(`ortak bileşenler: ${r.elements} öğenin bütün hesaplanmış stili .mon dışındakiyle aynı (kontrol: sızan kural ${r.control}+ fark üretti)`);
      });
      await page.waitForTimeout(300);
      await shot("06-detail.png");
      await shot("06b-detail-full.png", { full: true });

      // Önceki / sonraki (mürettebat içinde, döngüsel) ve seçili günün korunması
      const i = DEMO_CREW.indexOf(ID);
      const nextId = DEMO_CREW[(i + 1) % DEMO_CREW_SIZE];
      const prevId = DEMO_CREW[(i - 1 + DEMO_CREW_SIZE) % DEMO_CREW_SIZE];
      await check(current.issues, `önceki/sonraki: ${prevId} ‹ ${ID} › ${nextId}`, async () => {
        if (!(await page.locator('.ahc button[data-nav="prev"]').innerText()).includes(prevId)) throw new Error("önceki düğmesi");
        await page.locator(".ahc .strip button").first().click(); // gün 1
        await page.waitForURL(atDetail(ID, 1), { timeout: 5000 });
        await page.locator('.ahc button[data-nav="next"]').click();
        await page.waitForURL(atDetail(nextId, 1), { timeout: 5000 });
        await page.locator("#detail-h").getByText(nextId, { exact: true }).waitFor({ timeout: 5000 });
        await page.locator(".ahc .strip button[aria-current='true']").first().waitFor({ timeout: 10_000 });
        const sel = await page.locator(".ahc .ticks .sel").innerText();
        if (sel.trim() !== "1") throw new Error(`${nextId}'de seçili gün ${sel}`);
        await page.locator('.ahc button[data-nav="prev"]').click();
        await page.waitForURL(atDetail(ID, 1), { timeout: 5000 });
      });
      await page.locator(".ahc a.linkbtn").click();
      await page.locator("article[data-astronaut] .spark svg").nth(DEMO_CREW_SIZE - 1).waitFor({ timeout: 10_000 });
    });

    // ------------------------------------------------------------------ 6
    await step(`6. Mürettebat kartı: son etkinlik + 'Aktif'; akışta 'Sadece mürettebat'`, async () => {
      const card = page.locator(`article[data-astronaut="${ID}"]`);
      await check(current.issues, `${ID} kartında 'Aktif' rozeti (4. adımdaki öneri işareti)`, async () => {
        await page.locator(`article[data-astronaut="${ID}"][data-active="true"] .active-badge`).getByText("Aktif").waitFor({ timeout: 10_000 });
      });
      await check(current.issues, `${ID} kartında 'Son etkinlik … önce'`, async () => {
        const txt = await card.locator("[data-last-activity]").innerText();
        if (!/Son etkinlik/.test(txt) || !/(sn|dk) önce|şimdi/.test(txt)) throw new Error(`satır: ${txt}`);
      });
      await check(current.issues, "etkinliği eski / olmayan kartta rozet yok", async () => {
        const inactive = await page.locator('article[data-astronaut][data-active="false"]').count();
        const badges = await page.locator('article[data-active="false"] .active-badge').count();
        if (!inactive) throw new Error("bütün kartlar aktif görünüyor");
        if (badges) throw new Error("aktif olmayan kartta rozet var");
      });
      await shot("07-crew-active.png", { selector: `article[data-astronaut="${ID}"]` });

      const toggle = page.locator('button[data-filter="crew"]');
      const feedIds = () => page.locator("li[data-seq]").evaluateAll((els) => els.map((e) => e.getAttribute("data-astronaut") ?? ""));
      const before = await feedIds();
      await toggle.click();
      await check(current.issues, "'Sadece mürettebat' açık: akışta sadece mürettebat", async () => {
        if ((await toggle.getAttribute("aria-pressed")) !== "true") throw new Error("aria-pressed değil");
        await page.waitForFunction(
          (crew) => [...document.querySelectorAll("li[data-seq]")].every((e) => crew.includes(e.getAttribute("data-astronaut") ?? "")),
          [...DEMO_CREW],
          { timeout: 5000 },
        );
        const ids = await feedIds();
        if (!ids.length) throw new Error("akış boş");
      });
      const others = before.filter((x) => !DEMO_CREW.includes(x)).length;
      current.notes.push(`akış filtresi: kapalıyken ${before.length} olaydan ${others} tanesi mürettebat dışı; açıkken hepsi mürettebattan`);
      await shot("07b-feed-crew-only.png", { selector: ".mon-side" });
      await toggle.click();
      await check(current.issues, "'Sadece mürettebat' kapatılınca bütün olaylar", async () => {
        if ((await toggle.getAttribute("aria-pressed")) !== "false") throw new Error("aria-pressed hâlâ true");
        if (others)
          await page.waitForFunction(
            (crew) => [...document.querySelectorAll("li[data-seq]")].some((e) => !crew.includes(e.getAttribute("data-astronaut") ?? "")),
            [...DEMO_CREW],
            { timeout: 5000 },
          );
      });
    });

    await context.close();
  } finally {
    await browser?.close();
    // Tarayıcı kapandıktan sonra (denetim dışı): gemiyi dev:ship'teki yerine geri koy
    if (shipKilled) await restoreShip(tempShip, restoreNotes);
  }

  // ------------------------------------------------------------------ rapor
  console.log(`\n${c.bold}Dünya ekranı smoke raporu${c.off}  ${c.dim}(${web}/monitor · gemi ${SHIP} · Dünya ${EARTH}; görüntüler: ${OUT})${c.off}\n`);
  let failed = 0;
  for (const r of results) {
    const ok = r.issues.length === 0;
    if (!ok) failed++;
    console.log(`${ok ? `${c.green}✔` : `${c.red}✖`} ${r.name}${c.off} ${c.dim}${(r.ms / 1000).toFixed(1)} sn · ${r.files.join(", ") || "-"}${c.off}`);
    for (const n of r.notes) console.log(`    ${c.dim}${n}${c.off}`);
    for (const i of r.issues) console.log(`    ${c.red}${i.kind}${c.off}: ${i.text}`);
  }
  for (const n of restoreNotes) console.log(`${c.dim}Ortam: ${n}${c.off}`);
  console.log(failed ? `\n${c.red}${failed} adımda sorun var.${c.off}` : `\n${c.green}Dünya ekranı temiz.${c.off}`);
  return failed ? 1 : 0;
}
