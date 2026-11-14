/**
 * Astronot ekranının (/me) smoke testi (Playwright, headless Chromium).
 *
 * Çalıştır: `npm run smoke -- personal`. Ön koşul YOK: açık bir geliştirme sunucusu gerekmez.
 *
 * Test kendi kendine yeter: arayüzü derler (aynı adres) ve KENDİ geçici gemi backend'ini başlatır (port 8010, boş
 * ve atılabilir bir veritabanı); backend hem API'yi hem derlenmiş arayüzü servis eder — gerçek kurulumdaki
 * (`npm run serve`) gibi. Böylece geliştirme veritabanına (ship.db) ve çalışan sunuculara dokunulmaz, senaryo her
 * çalıştırmada baştan tekrarlanabilir (paylaşım geri alınamadığı için bu şart).
 *
 * Atılabilir dosyalar (derleme + veritabanı) depoda değil, sistemin geçici klasöründe durur ve sonunda geçici
 * backend'le birlikte silinir. Depoda sadece ekran görüntüleri ve geçici geminin logu kalır.
 *
 * Adımlar:
 *   1. Giriş kartı: kimlik aralığı /api/auth/hint'ten; EARTH girişi yok
 *   2. A000 ile giriş → bugünün ekranı (durum, şerit, yapılacaklar, check-in)
 *   3. Şeritte gün seçimi → geçmiş gün salt okunur (check-in yok, "Yaptım" yok); önceki/sonraki; sorunlu bir
 *      günde durum ikon + metinle; bugüne dönüş
 *   4. "Yaptım" → backend'e yazılır
 *   5. Bugünün check-in'i sonuna kadar → notlar, aktif mod satırı
 *   6. "Sadece skorlar" ile paylaşım → geminin downlink akışında `checkin.shared` olayı ruh hali / stres
 *      skorlarını taşır, cevap METNİNİ taşımaz
 *   7. Ayrıntılar (grafik iki çizgi + ölçümler) ve "tüm öz bakım çözümleri" penceresi
 *   8. Asistana sor (mock) + acil belirti kutusu; sohbet downlink'e girmez
 *   9. Başka bir astronotta check-in'de acil belirti → "Gemideki sağlık sorumlusu bilgilendirildi" kutusu;
 *      bu bilgi downlink'e girmez
 *  10. TR → EN; yenilemede oturum sürer; "Çıkış" token'ı siler
 *  11. Hesap değiştirme: önceki astronotun oturumundan hiçbir şey sonrakinin ekranına sızmaz — yeni astronotun
 *      verisi gelene kadar eski kimlik / şerit görünmez; çıkıştan SONRA dönen geç bir cevap da ekrana yazılmaz
 *  12. Oturum biterse (401) giriş kartına dönülür ve nedeni yazılır
 *  13. Terminal varlığı: girişte downlink'e `terminal.online` (yük sadece kimlik + durum + son görülme), sayfa
 *      açıkken zaman aşımı geçse de çevrimdışı olmaz, "Çıkış" → beklemeden `terminal.offline`, sekme kapanınca
 *      zaman aşımıyla `terminal.offline`; gizlilik notundaki "Dünya yalnızca terminalinin…" satırı
 *
 * Geçici gemide terminal süreleri kısadır (sinyal 1 sn, zaman aşımı 4 sn) ki 13. adım dakikalarca beklemesin.
 *
 * Ana durumların ekran görüntüleri 390 ve 1440 px'te, açık ve koyu temada alınır: screenshots/personal/.
 * Ayrıca: konsol hatası, yakalanmamış hata, başarısız istek, 4xx/5xx ve dış ağa istek olmamalı (offline);
 * ortak bileşenlerin ölçüleri prototipin CSS'indeki değerlerle aynı olmalı (başka bir stil dosyası sızmamalı).
 *
 * Ortam değişkenleri: SMOKE_PERSONAL_PORT (8010), SMOKE_ASTRONAUT (A000)
 * Çıkış kodu: 0 temiz · 1 sorun bulundu · 2 ön koşul yok (venv yok, port dolu, derleme başarısız)
 */
import { type ChildProcess, spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, openSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { type Browser, chromium, type Page } from "playwright";
import { build } from "vite";

// Port / süreç yardımcıları ortak modülde (npm run stop ve Dünya smoke testi de onu kullanır): scripts/ports.mjs
import { killPid, listeningPids } from "../../scripts/ports.mjs";

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = join(FRONTEND, "..");
const BACKEND = join(ROOT, "backend");
/** Ekran görüntüleri + geçici geminin logu (git'e girmez). */
const OUT = join(FRONTEND, "screenshots", "personal");
const TEMP_PORT = Number(process.env.SMOKE_PERSONAL_PORT ?? 8010);
/** Geçici geminin adresi: hem arayüz (/me) hem API (aynı adres, CORS gerekmez). */
const TEMP_API = `http://127.0.0.1:${TEMP_PORT}`;
const ID = process.env.SMOKE_ASTRONAUT?.trim().toUpperCase() || "A000";
/** Acil belirti (CMO kutusu) adımı için ikinci astronot: ilkinin check-in'i paylaşıldığı için baştan başlatılamaz. */
const ID2 = ID === "A001" ? "A002" : "A001";
/** Hesap değiştirme adımı için üçüncü astronot: check-in'i hiç başlamamış olmalı (geciken cevap ondan gelir). */
const ID3 = ["A003", "A004", "A005"].find((x) => x !== ID && x !== ID2) as string;
/** Terminal varlığı adımı için dördüncü astronot: o ana kadar terminali hiç açılmamış olmalı. */
const ID4 = ["A006", "A007", "A008", "A009"].find((x) => x !== ID && x !== ID2 && x !== ID3) as string;
/** Geçici gemideki terminal süreleri (saniye): sinyal aralığı, zaman aşımı, denetim aralığı. */
const PRESENCE = { heartbeat: 1, timeout: 4, sweep: 0.5 };
const LINK_TOKEN = "smoke-link-token";
const isWin = process.platform === "win32";
const VENV_PY = isWin ? join(BACKEND, ".venv", "Scripts", "python.exe") : join(BACKEND, ".venv", "bin", "python");

/**
 * Atılabilir dosyaların (derlenmiş arayüz + veritabanı) yeri: depo DIŞINDA, sistemin geçici klasöründe.
 * Depo klasörünü izleyen bir eşitleme / yedekleme istemcisi (OneDrive, Google Drive…) SQLite dosyalarını
 * yüklemeye çalışıp silindikten sonra geri getirebiliyor; geçici klasörde buna takılmaz.
 */
interface TempFiles { dir: string; dist: string; db: string }
function makeTempFiles(): TempFiles {
  const dir = mkdtempSync(join(tmpdir(), "ahm-smoke-personal-"));
  return { dir, dist: join(dir, "dist"), db: join(dir, "ship-smoke.db") };
}

type IssueKind = "console.error" | "pageerror" | "http" | "requestfailed" | "external" | "check";
interface Issue { kind: IssueKind; text: string }
interface StepResult { name: string; files: string[]; issues: Issue[]; notes: string[]; ms: number }
const c = { red: "\x1b[31m", green: "\x1b[32m", yellow: "\x1b[33m", dim: "\x1b[2m", bold: "\x1b[1m", off: "\x1b[0m" };

/** Ekran görüntüsü boyutları ve temaları (HealthRoot işletim sisteminin açık/koyu tercihini izler). */
const VARIANTS = [
  { width: 390, height: 844, scheme: "light" },
  { width: 390, height: 844, scheme: "dark" },
  { width: 1440, height: 900, scheme: "light" },
  { width: 1440, height: 900, scheme: "dark" },
] as const;

// ----------------------------------------------------------------------------- yardımcılar
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function reachable(url: string): Promise<boolean> {
  try {
    return (await fetch(url, { signal: AbortSignal.timeout(3000) })).ok;
  } catch {
    return false;
  }
}

async function waitUntil(fn: () => Promise<boolean>, timeoutMs: number, every = 500): Promise<boolean> {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    if (await fn().catch(() => false)) return true;
    await sleep(every);
  }
  return false;
}

/** Geçici gemiye doğrudan (sayfadan bağımsız) istek; durum denetimleri için. */
async function api<T>(method: string, path: string, token?: string, body?: unknown): Promise<T> {
  const r = await fetch(`${TEMP_API}${path}${path.includes("?") ? "&" : "?"}lang=tr`, {
    method,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${method} ${path} → ${r.status} ${await r.text()}`);
  return (await r.json()) as T;
}
const apiLogin = async (id: string) => (await api<{ token: string }>("POST", "/api/auth/login", undefined, { id, password: id })).token;

interface DownlinkEvent {
  seq: number;
  type: string;
  astronaut_id: string;
  payload: {
    share: string | null;
    day: {
      behavioral_hidden: boolean;
      area_scores: Record<string, number>;
      readings: Record<string, { today: number; used: number; level: number }>;
      checkin: { share: string; notes: { topic_key: string; flag: boolean; text: string | null }[] } | null;
    };
  };
}

/** terminal.online / terminal.offline: gün taşımaz, yük sadece varlık. */
interface TerminalEvent {
  seq: number;
  type: string;
  astronaut_id: string;
  day_index: number | null;
  ship_time: string;
  payload: Record<string, unknown> & { day: null; presence: { astronaut_id: string; state: string; last_seen: string } };
}
const isTerminalEvent = (e: { type: string }) => e.type.startsWith("terminal.");

/** Geminin downlink akışı (Dünya'nın okuduğu şey): `since`'ten sonraki olaylar + ham metin + son seq. */
async function downlink(since: number): Promise<{ events: DownlinkEvent[]; raw: string; lastSeq: number }> {
  const r = await fetch(`${TEMP_API}/api/downlink/stream?since=${since}&follow=false`, { headers: { Authorization: `Bearer ${LINK_TOKEN}` } });
  if (!r.ok) throw new Error(`downlink akışı → ${r.status} ${await r.text()}`);
  const raw = await r.text();
  const events: DownlinkEvent[] = [];
  let lastSeq = since;
  for (const block of raw.split(/\r?\n\r?\n/)) {
    const data = block.split(/\r?\n/).find((l) => l.startsWith("data:"));
    if (!data) continue;
    const json = JSON.parse(data.slice(5).trim());
    if (block.startsWith("id:")) events.push(json as DownlinkEvent);
    else if (typeof json.last_seq === "number") lastSeq = json.last_seq;
  }
  return { events, raw, lastSeq };
}

/**
 * Arayüzü test için derler (aynı adres: VITE_API_BASE_URL boş → API istekleri sayfanın geldiği sunucuya gider).
 * `npm run serve` ile aynı derleme; çıktı frontend/dist'e değil geçici klasöre yazılır, yani oradaki derlemeye
 * dokunulmaz.
 */
async function buildFrontend(dist: string): Promise<void> {
  process.env.VITE_API_BASE_URL = ""; // ortam değişkeni frontend/.env'deki değeri ezer
  await build({ root: FRONTEND, logLevel: "error", build: { outDir: dist, emptyOutDir: true } });
  if (!existsSync(join(dist, "index.html"))) throw new Error(`derleme çıktısı yok: ${dist}`);
}

/**
 * Geçici gemi: boş veritabanı (açılışta veri setinden dolar), hazır sorular, mock model, gecikmesiz downlink.
 * Derlenmiş arayüzü de kendisi servis eder (FRONTEND_DIST).
 */
async function startTempShip(tmp: TempFiles): Promise<ChildProcess> {
  const child = spawn(VENV_PY, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(TEMP_PORT)], {
    cwd: BACKEND,
    env: {
      ...process.env,
      STATION_ROLE: "ship",
      DATA_SOURCE: "astronaut_health",
      DATABASE_URL: `sqlite:///${tmp.db.replaceAll("\\", "/")}`,
      FRONTEND_DIST: tmp.dist,
      EARTH_LINK_TOKEN: LINK_TOKEN,
      CHECKIN_MODE: "scripted",
      LLM_PROVIDER: "mock",
      DOWNLINK_DELAY_SECONDS: "0",
      PRESENCE_HEARTBEAT_SECONDS: String(PRESENCE.heartbeat),
      PRESENCE_TIMEOUT_SECONDS: String(PRESENCE.timeout),
      PRESENCE_SWEEP_SECONDS: String(PRESENCE.sweep),
      PYTHONIOENCODING: "utf-8",
      PYTHONUTF8: "1",
    },
    stdio: ["ignore", openSync(join(OUT, "ship-smoke.log"), "w"), openSync(join(OUT, "ship-smoke.err.log"), "w")],
  });
  const ready = await waitUntil(async () => {
    const hint = (await (await fetch(`${TEMP_API}/api/auth/hint`, { signal: AbortSignal.timeout(3000) })).json()) as { astronauts: { count: number } | null };
    return (hint.astronauts?.count ?? 0) > 0 && (await reachable(`${TEMP_API}/me`));
  }, 120_000);
  if (!ready) {
    await stopTempShip(child);
    throw new Error(`geçici gemi ${TEMP_API} açılamadı (log: ${join(OUT, "ship-smoke.err.log")})`);
  }
  return child;
}

/** Geçici gemiyi kapatır ve port boşalana kadar bekler (Windows'ta veritabanı dosyası ancak o zaman silinebilir). */
async function stopTempShip(child: ChildProcess | null): Promise<void> {
  child?.kill();
  // Windows'ta venv başlatıcısı kapanır ama asıl Python süreci ayakta kalabilir: portu dinleyeni de kapat
  for (const pid of listeningPids(TEMP_PORT)) killPid(pid);
  await waitUntil(async () => listeningPids(TEMP_PORT).length === 0, 8000, 300);
}

/**
 * Geçici klasörü (derleme + veritabanı) siler. Windows'ta yeni kapanan sürecin dosyaları kısa süre kilitli
 * kalabilir: birkaç kez dener. Klasör gerçekten gittiyse true.
 */
async function removeTempFiles(tmp: TempFiles): Promise<boolean> {
  for (let i = 0; i < 20 && existsSync(tmp.dir); i++) {
    try {
      rmSync(tmp.dir, { recursive: true, force: true });
    } catch {
      await sleep(250);
    }
  }
  return !existsSync(tmp.dir);
}

function instrument(page: Page, report: (i: Issue) => void): void {
  const allowed = new Set([new URL(TEMP_API).host]);
  page.on("console", (m) => {
    if (m.type() === "error") report({ kind: "console.error", text: m.text() });
  });
  page.on("pageerror", (e) => report({ kind: "pageerror", text: e.message }));
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (u.protocol.startsWith("http") && !allowed.has(u.host)) report({ kind: "external", text: `dış ağa istek (offline kuralı): ${r.url()}` });
  });
  page.on("requestfailed", (r) => {
    const err = r.failure()?.errorText ?? "";
    if (!err.includes("ERR_ABORTED")) report({ kind: "requestfailed", text: `${r.method()} ${r.url()} — ${err}` });
  });
  page.on("response", (r) => {
    if (r.status() >= 400) report({ kind: "http", text: `${r.status()} ${r.request().method()} ${r.url()}` });
  });
}

async function check(issues: Issue[], what: string, fn: () => Promise<unknown>): Promise<boolean> {
  try {
    await fn();
    return true;
  } catch (e) {
    issues.push({ kind: "check", text: `${what}: ${(e as Error).message.split("\n")[0]}` });
    return false;
  }
}

function expect(cond: unknown, message: string): asserts cond {
  if (!cond) throw new Error(message);
}

// ----------------------------------------------------------------------------- ana akış
export async function runPersonalSmoke(): Promise<number> {
  if (!existsSync(VENV_PY)) {
    console.error(`${c.red}${VENV_PY} yok — önce kökte: npm run setup${c.off}`);
    return 2;
  }
  if (listeningPids(TEMP_PORT).length > 0) {
    console.error(`${c.red}Port ${TEMP_PORT} dolu (önceki bir smoke'tan kalmış olabilir). Kapatın: npm run stop -- --port ${TEMP_PORT}  (ya da SMOKE_PERSONAL_PORT ile başka port verin)${c.off}`);
    return 2;
  }

  rmSync(OUT, { recursive: true, force: true });
  mkdirSync(OUT, { recursive: true });
  const tmp = makeTempFiles();
  const warnIfTempLeft = async () => {
    if (!(await removeTempFiles(tmp))) console.error(`${c.yellow}geçici klasör silinemedi, elle silin: ${tmp.dir}${c.off}`);
  };
  try {
    process.stdout.write(`${c.dim}arayüz derleniyor (${tmp.dist})…${c.off}\n`);
    await buildFrontend(tmp.dist);
  } catch (e) {
    console.error(`${c.red}Arayüz derlenemedi: ${(e as Error).message.split("\n")[0]}${c.off}`);
    await warnIfTempLeft();
    return 2;
  }

  const marker = `SMOKE-${Date.now().toString(36).toUpperCase()}`;
  const results: StepResult[] = [];
  let browser: Browser | null = null;
  let tempShip: ChildProcess | null = null;

  try {
    process.stdout.write(`${c.dim}geçici gemi başlatılıyor (${TEMP_API}, boş veritabanı, derlenmiş arayüz)…${c.off}\n`);
    tempShip = await startTempShip(tmp);

    browser = await chromium.launch();
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "tr-TR", colorScheme: "light" });
    await context.addInitScript(() => {
      try {
        if (!localStorage.getItem("ahm-lang")) localStorage.setItem("ahm-lang", "tr");
      } catch {
        /* yok say */
      }
    });
    const page = await context.newPage();

    let current: StepResult = { name: "", files: [], issues: [], notes: [], ms: 0 };
    /** Sadece "oturum bitti" adımında açılır: orada 401 beklenen cevaptır, sorun sayılmaz. */
    let expect401 = false;
    instrument(page, (i) => {
      const is401 = (i.kind === "http" && i.text.startsWith("401 ")) || (i.kind === "console.error" && i.text.includes("401"));
      if (!(expect401 && is401)) current.issues.push(i);
    });

    /**
     * Prototip sadakati: seçilen öğenin hesaplanmış stili, prototipin CSS'indeki değerle aynı olmalı
     * (frontend/reference/personal-artifact.html). Başka bir stil dosyası ortak bileşenlere sızarsa burada yakalanır.
     */
    const expectStyle = async (selector: string, want: Record<string, string>) => {
      const got = await page.evaluate(
        ([sel, props]) => {
          const el = document.querySelector(sel as string);
          if (!el) return null;
          const cs = getComputedStyle(el);
          return Object.fromEntries((props as string[]).map((p) => [p, cs.getPropertyValue(p)]));
        },
        [selector, Object.keys(want)] as const,
      );
      expect(got, `${selector} bulunamadı`);
      for (const [prop, value] of Object.entries(want)) expect(got[prop] === value, `${selector} ${prop} = ${got[prop]} (prototip: ${value})`);
    };

    /** Aynı durumu 390 / 1440 px ve açık / koyu temada kaydeder; sonunda 1440 açık temaya döner. */
    const shots = async (name: string) => {
      for (const v of VARIANTS) {
        await page.setViewportSize({ width: v.width, height: v.height });
        await page.emulateMedia({ colorScheme: v.scheme });
        await page.waitForTimeout(250); // grafik yeniden ölçülür, çubuk geçişi biter
        const file = `${name}-${v.width}-${v.scheme}.png`;
        await page.screenshot({ path: join(OUT, file), fullPage: true });
        current.files.push(`personal/${file}`);
      }
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.emulateMedia({ colorScheme: "light" });
    };
    const shot = async (file: string) => {
      await page.screenshot({ path: join(OUT, file), fullPage: true });
      current.files.push(`personal/${file}`);
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

    const strip = page.locator(".strip");
    const dayButton = (day: number) => strip.getByRole("button", { name: new RegExp(`^(Gün|Day) ${day}:`) });
    const checkinCard = page.locator("section[aria-label='Günlük check-in'], section[aria-label='Daily check-in']");
    const submitLogin = async (id: string) => {
      await page.locator("#me-id").fill(id);
      await page.locator("#me-pw").fill(id);
      await page.getByRole("button", { name: "Giriş yap" }).click();
    };
    const dashboardReady = async () => {
      await strip.getByRole("button").nth(29).waitFor({ timeout: 20_000 });
      await page.locator(".todo h2").waitFor({ timeout: 10_000 });
    };
    const loginAs = async (id: string) => {
      await submitLogin(id);
      await dashboardReady();
    };
    /**
     * Bir isteğin cevabını tarayıcıya geç ulaştırır (yavaş ağ / yavaş model): backend isteği hemen işler, cevap
     * `release()` çağrılana kadar bekletilir. `release()` cevap sayfaya teslim edilince döner.
     */
    const holdResponse = async (url: RegExp) => {
      let open!: () => void;
      const gate = new Promise<void>((resolve) => (open = resolve));
      let delivered = false;
      await page.route(url, async (route) => {
        const response = await route.fetch();
        await gate;
        await route.fulfill({ response });
        delivered = true;
      });
      return async () => {
        open();
        expect(await waitUntil(async () => delivered, 10_000, 50), `bekletilen cevap teslim edilemedi: ${url}`);
      };
    };

    // ------------------------------------------------------------------ 1
    await step("1. Giriş kartı (kimlik aralığı API'den, EARTH girişi yok)", async () => {
      await page.goto(`${TEMP_API}/me`);
      await page.locator("#me-id").waitFor({ timeout: 20_000 });
      const hint = await api<{ astronauts: { first_id: string; last_id: string; count: number }; text: string }>("GET", "/api/auth/hint");
      await check(current.issues, "ipucu metni API'den", () => page.getByText(hint.text, { exact: true }).waitFor({ timeout: 10_000 }));
      await check(current.issues, "kimlik aralığı kalın yazılı", async () => {
        const bold = await page.locator(".login b").allInnerTexts();
        expect(bold.includes(hint.astronauts.first_id) && bold.includes(hint.astronauts.last_id), `kalın: ${bold.join(", ")}`);
      });
      await check(current.issues, "giriş kartında EARTH yok", async () => {
        const text = await page.locator(".login").innerText();
        expect(!/EARTH|Dünya üssü/i.test(text), "giriş kartı EARTH'ten söz ediyor");
        expect((await page.locator("#me-id").getAttribute("placeholder")) === hint.astronauts.first_id, "yer tutucu ilk kimlik değil");
      });
      await check(current.issues, "üst barda TR/EN seçimi", async () => {
        expect((await page.locator(".langseg button[aria-pressed='true']").innerText()) === "TR", "TR seçili değil");
      });
      await check(current.issues, "prototip ölçüleri: giriş kartı", async () => {
        await expectStyle(".ahc .login", { "max-width": "420px", "row-gap": "12px" });
        await expectStyle(".ahc .field label", { "font-size": "13px", "font-weight": "600" });
        await expectStyle(".ahc > main", { "max-width": "680px" });
      });
      await shots("01-login");
    });

    // ------------------------------------------------------------------ 2
    await step(`2. ${ID} ile giriş → bugünün ekranı`, async () => {
      await loginAs(ID);
      const me = await api<{ astronaut: { id: string; mission_label: string }; today: number }>("GET", "/api/me", await apiLogin(ID));
      await check(current.issues, "üst barda kim", async () => {
        expect((await page.locator(".whoami").innerText()) === `${ID} · ${me.astronaut.mission_label}`, await page.locator(".whoami").innerText());
      });
      await check(current.issues, "token sekme oturumunda", async () => {
        expect(await page.evaluate(() => !!sessionStorage.getItem("ahm-token") && !localStorage.getItem("ahm-token")), "token sessionStorage'da değil");
      });
      await check(current.issues, "bugün seçili", async () => {
        expect((await strip.locator("button[aria-current='true']").getAttribute("aria-label"))?.startsWith(`Gün ${me.today}:`), "seçili gün bugün değil");
      });
      await check(current.issues, "check-in ilk sorusu", () => checkinCard.getByText("Dün gece nasıl uyudunuz?").waitFor({ timeout: 10_000 }));
      await check(current.issues, "aktif mod satırı", () => checkinCard.getByText("Hazır sorular, model çevrim dışı").waitFor({ timeout: 5000 }));
      await check(current.issues, "prototip yazı tipleri yüklü", async () => {
        const ok = await page.evaluate(async () => {
          await document.fonts.ready;
          return document.fonts.check('700 22px "Archivo"') && document.fonts.check('400 15px "IBM Plex Sans"');
        });
        expect(ok, "Archivo / IBM Plex Sans yüklenmedi");
      });
      await shots("02-today");
    });

    // ------------------------------------------------------------------ 3
    await step("3. Şeritte gün seçimi → geçmiş gün salt okunur; önceki/sonraki; sorunlu gün; bugüne dönüş", async () => {
      await dayButton(12).click();
      await check(current.issues, "gün 12 seçildi", async () => {
        await strip.locator("button[aria-current='true'][aria-label^='Gün 12:']").waitFor({ timeout: 5000 });
        await page.locator(".dayrow span", { hasText: /^30 günün 12\. günü/ }).waitFor({ timeout: 5000 });
      });
      await check(current.issues, "geçmiş günde check-in salt okunur", async () => {
        await checkinCard.getByText("Bu gün için kaydedilmiş bir check-in yok.").waitFor({ timeout: 5000 });
        expect((await checkinCard.locator("input").count()) === 0, "geçmiş günde cevap alanı var");
      });
      await check(current.issues, "geçmiş günde 'Yaptım' yok", async () => {
        await page.locator(".todo[data-audience='astronaut']").waitFor();
        await page.waitForFunction(() => !document.querySelector("[aria-busy='true']"));
        expect((await page.locator(".donebtn").count()) === 0, "geçmiş günde Yaptım düğmesi var");
      });
      await shot("03-past-day-1440-light.png");
      await page.getByRole("button", { name: "Sonraki gün" }).click();
      await check(current.issues, "sonraki gün → 13", () => strip.locator("button[aria-current='true'][aria-label^='Gün 13:']").waitFor({ timeout: 5000 }));
      await page.getByRole("button", { name: "Önceki gün" }).click();
      await page.getByRole("button", { name: "Önceki gün" }).click();
      await check(current.issues, "önceki gün ×2 → 11", () => strip.locator("button[aria-current='true'][aria-label^='Gün 11:']").waitFor({ timeout: 5000 }));
      // Sorunlu bir gün (şeritte renkli çubuk): durum başlıkta ikon + metinle verilir, sadece renkle değil
      const troubled = strip.locator("button.s1, button.s2").first();
      if ((await troubled.count()) > 0) {
        const label = (await troubled.getAttribute("aria-label")) ?? "";
        await troubled.click();
        await check(current.issues, "sorunlu günde durum: ikon + metin, prototip ölçüsü", async () => {
          await page.locator(".state .glyph").waitFor({ timeout: 5000 });
          expect(!(await page.locator(".state").innerText()).includes("Normal"), `başlık hâlâ Normal (${label})`);
          await expectStyle(".ahc .state .glyph", { width: "13px", height: "13px" });
        });
        // Görüntü günün verisi geldikten sonra alınsın (başlık şeritten hemen dolar, gerisi istekle gelir)
        const troubledDay = /^Gün (\d+):/.exec(label)?.[1];
        if (troubledDay) await page.locator(".dayrow span", { hasText: new RegExp(`^30 günün ${troubledDay}\\. günü`) }).waitFor({ timeout: 5000 });
        await page.waitForFunction(() => !document.querySelector("[aria-busy='true'], .waiting"), undefined, { timeout: 5000 });
        await page.mouse.move(5, 5);
        await shot("03b-attention-day-1440-light.png");
      } else current.notes.push(`${ID} için şeritte sorunlu gün yok; ikon denetimi atlandı`);
      await dayButton(30).click();
      await check(current.issues, "bugüne dönüş", () => checkinCard.locator("input").waitFor({ timeout: 5000 }));
    });

    // ------------------------------------------------------------------ 4
    await step("4. 'Yaptım' → backend'e yazılır", async () => {
      const token = await apiLogin(ID);
      const before = await api<{ todo: { code: string; done: boolean }[] }>("GET", "/api/me/days/30", token);
      if (before.todo.length === 0) {
        current.notes.push(`${ID} için bugün yapılacak öğe yok; adım atlandı`);
        return;
      }
      const item = page.locator(".todo .item").first();
      const code = await item.getAttribute("data-code");
      const button = item.locator(".donebtn");
      expect((await button.getAttribute("aria-pressed")) === "false", "başta basılı");
      await button.click();
      await check(current.issues, "basılı durum (ikon + aria-pressed)", async () => {
        await item.locator(".donebtn[aria-pressed='true']").waitFor({ timeout: 5000 });
        expect((await button.innerText()).includes("✓"), "✓ işareti yok");
      });
      await check(current.issues, "backend'de işaretli", async () => {
        const after = await api<{ todo: { code: string; done: boolean }[] }>("GET", "/api/me/days/30", token);
        expect(after.todo.find((x) => x.code === code)?.done === true, `${code} backend'de işaretli değil`);
      });
      await check(current.issues, "adımlar açılır", async () => {
        await item.locator("summary").click();
        await item.locator("ol li").first().waitFor({ timeout: 3000 });
        await item.locator("summary").click();
      });
    });

    // ------------------------------------------------------------------ 5
    let cursor = 0;
    const answers = [`Kötü uyudum ${marker}`, `Şöyle böyle ${marker}`, `Biraz ${marker}`];
    await step("5. Bugünün check-in'i sonuna kadar", async () => {
      cursor = (await downlink(0)).lastSeq;
      const input = checkinCard.locator("input");
      const questions = ["Dün gece nasıl uyudunuz?", "Bugün ruh haliniz nasıl?", "Bugün sizi strese sokan bir şey var mı?"];
      for (let i = 0; i < answers.length; i++) {
        await checkinCard.locator(".msg.bot", { hasText: questions[i] }).waitFor({ timeout: 10_000 });
        await input.fill(answers[i]);
        await input.press("Enter");
      }
      await checkinCard.locator(".msg.bot", { hasText: "Herhangi bir belirtiniz var mı?" }).waitFor({ timeout: 10_000 });
      await checkinCard.getByRole("button", { name: "Yok", exact: true }).click();
      await checkinCard.locator(".msg.bot", { hasText: "başka bir şey var mı?" }).waitFor({ timeout: 10_000 });
      await checkinCard.getByRole("button", { name: "Hayır", exact: true }).click();
      await check(current.issues, "tamamlandı mesajı", () => checkinCard.locator(".msg.bot", { hasText: /^Check-in tamamlandı\./ }).waitFor({ timeout: 10_000 }));
      await check(current.issues, "cevap alanı kapandı", async () => {
        expect(await input.isDisabled(), "cevap alanı hâlâ açık");
        expect((await input.getAttribute("placeholder")) === "Check-in tamamlandı", "yer tutucu değişmedi");
      });
      await check(current.issues, "notlar (konu + cevap, işaretli olan ikon + metinle)", async () => {
        const notes = await checkinCard.locator(".cinotes > div").allInnerTexts();
        expect(notes.length === 4, `not sayısı ${notes.length}`);
        expect(notes[0].includes(answers[0]) && notes[0].includes("işaretlendi"), `uyku notu: ${notes[0]}`);
        expect((await checkinCard.locator(".cinotes > div").first().locator(".glyph.g1").count()) === 1, "işaretli notta ikon yok");
        await expectStyle(".ahc .cinotes .glyph", { width: "10px", height: "10px" });
      });
      await check(current.issues, "backend'de tamamlandı ve gizli", async () => {
        const st = await api<{ done: boolean; share: string | null; can_reset: boolean; mode: string }>("GET", "/api/checkin", await apiLogin(ID));
        expect(st.done && st.share === "private" && st.can_reset && st.mode === "scripted", JSON.stringify(st));
      });
      await check(current.issues, "paylaşım seçenekleri", () => checkinCard.getByRole("button", { name: "Sadece skorlar" }).waitFor({ timeout: 5000 }));
      await shots("04-checkin-done");
    });

    // ------------------------------------------------------------------ 6
    await step("6. 'Sadece skorlar' ile paylaş → downlink'te skor var, cevap metni yok", async () => {
      await checkinCard.getByRole("button", { name: "Sadece skorlar" }).click();
      await check(current.issues, "seçim basılı, 'Gizli tut' kapalı, 'Baştan başla' yok", async () => {
        await checkinCard.locator("button[data-level='scores'][aria-pressed='true']").waitFor({ timeout: 10_000 });
        expect(await checkinCard.locator("button[data-level='private']").isDisabled(), "'Gizli tut' hâlâ seçilebilir");
        expect((await checkinCard.getByRole("button", { name: "Baştan başla" }).count()) === 0, "'Baştan başla' hâlâ var");
        await checkinCard.getByText(/sözlerinizi görmez\. Paylaşım geri alınamaz\./).waitFor({ timeout: 5000 });
      });
      const { events, raw } = await downlink(cursor);
      const mine = events.filter((e) => e.astronaut_id === ID);
      const completed = mine.find((e) => e.type === "checkin.completed");
      const shared = mine.find((e) => e.type === "checkin.shared");
      await check(current.issues, "checkin.shared olayı geldi", async () => expect(shared, `olaylar: ${mine.map((e) => e.type).join(", ") || "yok"}`));
      if (shared) {
        const day = shared.payload.day;
        await check(current.issues, "paylaşım seviyesi scores", async () => expect(shared.payload.share === "scores" && day.checkin?.share === "scores", JSON.stringify(day.checkin)));
        await check(current.issues, "ruh hali ve stres skoru VAR", async () => {
          for (const col of ["beh_mood_score", "beh_stress_score"]) {
            const r = day.readings[col];
            expect(r && typeof r.today === "number" && typeof r.used === "number", `${col} olayda yok`);
          }
          expect(day.behavioral_hidden === false && typeof day.area_scores.behavioral === "number", "davranışsal alan skoru yok");
          current.notes.push(`checkin.shared seq ${shared.seq}: ruh hali ${day.readings.beh_mood_score.used.toFixed(1)}, stres ${day.readings.beh_stress_score.used.toFixed(1)}`);
        });
        await check(current.issues, "cevap METNİ YOK (notlarda text = null)", async () => {
          const notes = day.checkin?.notes ?? [];
          expect(notes.length === 4 && notes.every((n) => n.text === null), JSON.stringify(notes));
          expect(notes.find((n) => n.topic_key === "sleep")?.flag === true, "uyku konusu işaretli gelmedi");
        });
      }
      await check(current.issues, "cevap metni akışın HİÇBİR yerinde yok", async () => {
        for (const needle of [marker, "Kötü uyudum", "Şöyle böyle", "Biraz "]) expect(!raw.includes(needle), `akışta "${needle}" geçiyor`);
        expect(!/"messages"|"urgent"|cmo/i.test(raw), "akışta mesaj / urgent / CMO alanı var");
      });
      await check(current.issues, "paylaşılmadan önceki olayda ruh hali / stres yok", async () => {
        expect(completed, "checkin.completed olayı yok");
        const day = completed.payload.day;
        expect(completed.payload.share === "private" && day.checkin?.notes.length === 0, JSON.stringify(day.checkin));
        expect(!("beh_mood_score" in day.readings) && !("beh_stress_score" in day.readings) && day.behavioral_hidden, "gizli tutulan check-in'de ruh hali / stres gitmiş");
      });
      await shots("05-shared");
    });

    // ------------------------------------------------------------------ 7
    await step("7. Ayrıntılar (grafik iki çizgi + ölçümler) ve öz bakım penceresi", async () => {
      const details = page.locator("details.more", { has: page.locator("summary", { hasText: "Bu günün ayrıntıları" }) });
      await details.locator("summary").click();
      await check(current.issues, "grafik: kümülatif + tek gün, 80 ve 65 çizgileri", async () => {
        await details.locator(".chart svg").waitFor({ timeout: 5000 });
        expect((await details.locator(".chart svg path").count()) === 2, "grafikte iki çizgi yok");
        expect((await details.locator(".legend span").count()) === 2, "açıklamada iki seri yok");
        await details.locator(".chart svg text", { hasText: "80 ve üzeri normal" }).waitFor({ timeout: 3000 });
        await details.locator(".chart svg text", { hasText: "65 altı rahatsız" }).waitFor({ timeout: 3000 });
      });
      await check(current.issues, "ölçümler tablosu + tek dipnot", async () => {
        expect((await details.locator("table.readings tr[data-col]").count()) === 18, "18 ölçüm satırı yok");
        await details.getByText("Aralıklar simüle veri setinden alınmıştır, tıbbi doğrulama yapılmamıştır.").waitFor({ timeout: 3000 });
        expect((await details.locator("tr[data-col='beh_mood_score'] td").nth(1).innerText()) !== "Paylaşılmadı", "astronot kendi ruh halini göremiyor");
      });
      await check(current.issues, "prototip ölçüleri: grafik açıklaması ve tablo işaretleri", async () => {
        // açık tema: --ink-2 = #47525f
        await expectStyle(".ahc .legend", { "column-gap": "16px", "font-size": "13px", color: "rgb(71, 82, 95)", "margin-top": "4px", "margin-bottom": "6px" });
        if ((await details.locator("table.readings .glyph").count()) > 0) await expectStyle(".ahc table.readings .glyph", { width: "10px", height: "10px" });
        else current.notes.push("tabloda aralık dışı ölçüm yok; işaret ölçüsü denetlenmedi");
      });
      await check(current.issues, "kimlik satırı", () => details.locator(".who").getByText("Simülasyon deseni").waitFor({ timeout: 3000 }));
      await check(current.issues, "grafiğe tıklama gün seçer", async () => {
        const box = await details.locator(".chart svg").boundingBox();
        expect(box, "grafik kutusu yok");
        await page.mouse.click(box.x + 30 + ((box.width - 40) * 19) / 29, box.y + 60);
        await strip.locator("button[aria-current='true'][aria-label^='Gün 20:']").waitFor({ timeout: 5000 });
        await dayButton(30).click();
        await page.mouse.move(5, 5);
      });
      await shots("06-details");
      await page.locator(".infobtn").click();
      const dialog = page.locator("dialog");
      await check(current.issues, "pencere: 14 çözüm, Esc kapatır", async () => {
        await dialog.getByRole("heading", { name: "Tüm öz bakım çözümleri" }).waitFor({ timeout: 5000 });
        expect((await dialog.locator("details.sol").count()) === 14, "14 çözüm yok");
        await dialog.locator("details.sol summary").first().click();
        await dialog.getByText(/^Ne zaman:/).first().waitFor({ timeout: 3000 });
        await shot("07-selfcare-dialog-1440-light.png");
        await page.keyboard.press("Escape");
        await page.waitForFunction(() => !document.querySelector("dialog")?.open);
      });
      await details.locator("summary").click();
    });

    // ------------------------------------------------------------------ 8
    await step("8. Asistana sor (mock) + acil belirti kutusu; sohbet gemide kalır", async () => {
      const before = (await downlink(0)).lastSeq;
      const ask = page.locator("details.ask");
      expect(!(await ask.evaluate((d) => (d as HTMLDetailsElement).open)), "'Asistana sor' varsayılan olarak açık");
      await ask.locator("summary").click();
      await check(current.issues, "sohbetin gemide kaldığı notu", () => ask.getByText("Bu sohbet gemide kalır, Dünya'ya gönderilmez.", { exact: true }).waitFor({ timeout: 3000 }));
      const input = ask.locator("input");
      await input.fill("Bugün durumum nasıl?");
      await input.press("Enter");
      await check(current.issues, "asistan cevabı (akış bitti)", async () => {
        await ask.locator(".msg.bot[data-settled='true']").first().waitFor({ timeout: 30_000 });
        const text = await ask.locator(".msg.bot").first().innerText();
        expect(text.length > 40 && /30/.test(text), `cevap: ${text.slice(0, 120)}`);
        current.notes.push(`asistan: ${text.slice(0, 90).replace(/\s+/g, " ")}…`);
      });
      await shots("08-assistant");
      await input.fill("Göğsümde ağrı var ve nefes almakta zorlanıyorum");
      await input.press("Enter");
      await check(current.issues, "acil belirti kutusu (kural tabanlı)", async () => {
        const box = ask.locator("[data-emergency]");
        await box.waitFor({ timeout: 30_000 });
        await box.getByText(/Gemideki sağlık sorumlusu bilgilendirildi\./).waitFor({ timeout: 5000 });
        expect((await box.locator("ol li").count()) > 0, "protokol adımları yok");
        await box.getByText("Bu protokol metni yer tutucudur; tıbbi doğrulaması yapılmamıştır.").waitFor({ timeout: 3000 });
        await ask.locator(".msg.bot[data-settled='true']").nth(1).waitFor({ timeout: 30_000 });
      });
      await shot("09-assistant-emergency-1440-light.png");
      await check(current.issues, "sohbet ve acil durum downlink'e girmedi", async () => {
        const { events: all, raw } = await downlink(before);
        // Terminal varlığı olayları (terminal.*) içerik taşımaz; sohbetin ürettiği olay sayılmaz (13. adım ayrıca sınar)
        const events = all.filter((e) => !isTerminalEvent(e));
        expect(events.length === 0, `sohbetten sonra ${events.length} yeni olay: ${events.map((e) => e.type).join(", ")}`);
        expect(!/Göğsümde|durumum nasıl/.test(raw), "sohbet metni akışta");
      });
      await ask.locator("summary").click();
    });

    // ------------------------------------------------------------------ 9
    await step(`9. ${ID2}: check-in'de acil belirti → 'sağlık sorumlusu bilgilendirildi' kutusu, Dünya'ya gitmez`, async () => {
      await page.getByRole("button", { name: "Çıkış" }).click();
      await page.locator("#me-id").waitFor({ timeout: 10_000 });
      await loginAs(ID2);
      await check(current.issues, "yeni astronotta önceki astronotun verisi yok", async () => {
        expect((await page.locator(".whoami").innerText()).startsWith(`${ID2} ·`), await page.locator(".whoami").innerText());
        expect(!(await checkinCard.innerText()).includes(marker), "önceki astronotun cevapları görünüyor");
        expect(await page.locator("details.ask").evaluate((d) => !(d as HTMLDetailsElement).open && !d.querySelector(".msg")), "önceki sohbet duruyor");
      });
      const since = (await downlink(0)).lastSeq;
      const urgent = `nefes almakta zorlanıyorum ${marker}`;
      for (const name of ["İyi", "İyi", "Hayır"]) {
        const n = await checkinCard.locator(".msg.me").count();
        await checkinCard.getByRole("button", { name, exact: true }).click();
        await checkinCard.locator(".msg.me").nth(n).waitFor({ timeout: 10_000 });
        await page.waitForFunction(() => !document.querySelector(".msg.pending"));
      }
      await checkinCard.locator(".msg.bot", { hasText: "Herhangi bir belirtiniz var mı?" }).waitFor({ timeout: 10_000 });
      await checkinCard.locator("input").fill(urgent);
      await checkinCard.locator("input").press("Enter");
      await check(current.issues, "kutu: Gemideki sağlık sorumlusu bilgilendirildi", async () => {
        const box = checkinCard.locator("[data-cmo]");
        await box.waitFor({ timeout: 10_000 });
        expect((await box.innerText()).startsWith("Gemideki sağlık sorumlusu bilgilendirildi."), await box.innerText());
        expect((await box.innerText()).includes("Dünya'ya gönderilmedi"), "kutuda 'Dünya'ya gönderilmedi' yok");
      });
      await checkinCard.getByRole("button", { name: "Hayır", exact: true }).click();
      await checkinCard.locator(".msg.bot", { hasText: /^Check-in tamamlandı\./ }).waitFor({ timeout: 10_000 });
      await shots("10-cmo");
      await check(current.issues, "acil belirti ve CMO bilgisi downlink'te yok", async () => {
        const { raw, events } = await downlink(since);
        expect(events.some((e) => e.type === "checkin.completed" && e.astronaut_id === ID2), "checkin.completed gelmedi");
        expect(!raw.includes(marker) && !raw.includes("nefes") && !/urgent|cmo/i.test(raw), "acil belirti bilgisi akışta");
      });
    });

    // ------------------------------------------------------------------ 10
    await step("10. TR → EN; yenilemede oturum sürer; 'Çıkış' token'ı siler", async () => {
      await page.locator(".langseg").getByRole("button", { name: "EN" }).click();
      await check(current.issues, "ekran İngilizce (çerçeve + backend metinleri birlikte)", async () => {
        await page.getByRole("heading", { name: "Astronaut Health Check" }).waitFor({ timeout: 10_000 });
        await page.locator(".todo h2", { hasText: "To do" }).waitFor({ timeout: 10_000 });
        await page.locator(".dayrow span", { hasText: /^Day 30 of 30/ }).waitFor({ timeout: 10_000 });
        await checkinCard.getByText("Scripted questions, model offline").waitFor({ timeout: 10_000 });
        await page.getByRole("button", { name: "Log out" }).waitFor({ timeout: 5000 });
      });
      await shot("11-english-1440-light.png");
      await page.reload();
      await check(current.issues, "yenilemeden sonra giriş korunur (sekme oturumu) ve dil kalır", async () => {
        await strip.getByRole("button").nth(29).waitFor({ timeout: 20_000 });
        await page.getByRole("heading", { name: "Astronaut Health Check" }).waitFor({ timeout: 5000 });
        expect((await page.locator(".whoami").innerText()).startsWith(`${ID2} ·`), "yenilemeden sonra kimlik yok");
      });
      await page.locator(".langseg").getByRole("button", { name: "TR" }).click();
      await page.getByRole("button", { name: "Çıkış" }).click();
      await check(current.issues, "çıkış: giriş kartı, token silindi", async () => {
        await page.locator("#me-id").waitFor({ timeout: 10_000 });
        expect(await page.evaluate(() => sessionStorage.getItem("ahm-token") === null), "token silinmedi");
        expect((await page.locator(".whoami").count()) === 0, "çıkıştan sonra kimlik görünüyor");
      });
    });

    // ------------------------------------------------------------------ 11
    await step(`11. Hesap değiştirme: ${ID3} → ${ID2}; önceki oturumdan hiçbir şey sızmaz (geciken cevaplar dahil)`, async () => {
      await loginAs(ID3);
      // ID3'ün cevabı gemiye yazılır ama cevabın dönüşü gecikir (yavaş model gibi); bu sırada çıkış yapılır.
      const late = `GEC-${marker}`;
      const releaseTurn = await holdResponse(/\/api\/checkin\/turn\?/);
      await checkinCard.locator("input").fill(late);
      await checkinCard.locator("input").press("Enter");
      await checkinCard.locator(".msg.pending").waitFor({ timeout: 5000 });
      await page.getByRole("button", { name: "Çıkış" }).click();
      await page.locator("#me-id").waitFor({ timeout: 10_000 });

      // Sonraki astronot girer; kendi verisi gelene kadar ekranda öncekinden hiçbir şey olmamalı.
      const releaseMe = await holdResponse(/\/api\/me\?/);
      await submitLogin(ID2);
      await page.getByRole("button", { name: "Çıkış" }).waitFor({ timeout: 10_000 });
      await check(current.issues, "yeni oturum yüklenirken önceki astronotun kimliği / şeridi görünmez", async () => {
        // allInnerTexts beklemez (innerText öğe yokken 30 sn beklerdi)
        expect((await page.locator(".whoami").count()) === 0, `üst barda kimlik: ${(await page.locator(".whoami").allInnerTexts()).join(", ")}`);
        expect((await strip.count()) === 0, "önceki astronotun 30 günlük şeridi görünüyor");
        expect(!(await page.locator(".ahc").innerText()).includes(ID3), `ekranda ${ID3} geçiyor`);
      });
      await releaseMe();
      await dashboardReady();
      await check(current.issues, "yeni oturumun kimliği", async () => {
        expect((await page.locator(".whoami").innerText()).startsWith(`${ID2} ·`), await page.locator(".whoami").innerText());
      });

      // Şimdi ID3'ün geciken cevabı döner: ID2'nin ekranına yazılmamalı.
      await releaseTurn();
      await page.waitForTimeout(500);
      await check(current.issues, "çıkıştan sonra dönen cevap sonraki astronotun ekranına yazılmaz", async () => {
        expect(!(await page.locator(".ahc").innerText()).includes(late), `${ID3}'ün cevabı ${ID2}'nin ekranında görünüyor`);
        expect((await page.locator(".whoami").innerText()).startsWith(`${ID2} ·`), await page.locator(".whoami").innerText());
      });
      await check(current.issues, "geciken cevap gemide kayıtlı (denetim gerçekten geç cevabı sınadı)", async () => {
        const st = await api<{ messages: { who: string; text: string }[] }>("GET", "/api/checkin", await apiLogin(ID3));
        expect(st.messages.some((m) => m.text.includes(late)), `${ID3}'ün cevabı gemide yok`);
      });
      await page.unrouteAll({ behavior: "wait" });
    });

    // ------------------------------------------------------------------ 12
    await step("12. Oturum biterse (401) giriş kartına dönülür ve nedeni yazılır", async () => {
      // Token geçersizleşir (süresi dolmuş / istasyon sıfırlanmış gibi); sonraki istek 401 döner.
      expect401 = true;
      await page.evaluate(() => sessionStorage.setItem("ahm-token", "gecersiz-token"));
      await dayButton(5).click();
      await check(current.issues, "giriş kartı, neden yazılı, token silindi, astronotun verisi ekranda değil", async () => {
        await page.locator("#me-id").waitFor({ timeout: 10_000 });
        const why = (await page.locator(".login [role='alert']").allInnerTexts()).join(" ").trim();
        expect(why.length > 0, "giriş kartında neden yazmıyor");
        current.notes.push(`mesaj: ${why}`);
        expect(await page.evaluate(() => sessionStorage.getItem("ahm-token") === null), "token silinmedi");
        expect((await page.locator(".whoami").count()) === 0 && (await strip.count()) === 0, "oturum bittikten sonra astronotun verisi ekranda");
      });
      expect401 = false;
    });

    // ------------------------------------------------------------------ 13
    await step(`13. Terminal varlığı (${ID4}): girişte çevrimiçi, açıkken sürer, çıkışta hemen, sekme kapanınca zaman aşımıyla çevrimdışı`, async () => {
      const beats: { at: number; leaving: boolean }[] = [];
      page.on("request", (r) => {
        if (r.method() === "POST" && r.url().includes("/api/me/presence")) beats.push({ at: Date.now(), leaving: (r.postData() ?? "").includes('"leaving":true') });
      });
      let since = (await downlink(0)).lastSeq;
      /** `since`'ten sonra ID4 için terminal.<state> olayı gelene kadar bekler; olayı, akışın ham metnini ve süreyi döner. */
      const waitTerminal = async (state: "online" | "offline", timeoutMs: number): Promise<{ ev: TerminalEvent; raw: string; ms: number }> => {
        const t0 = Date.now();
        let found: TerminalEvent | undefined;
        let raw = "";
        await waitUntil(async () => {
          const r = await downlink(since);
          raw = r.raw;
          found = (r.events as unknown as TerminalEvent[]).find((e) => e.type === `terminal.${state}` && e.astronaut_id === ID4);
          return found !== undefined;
        }, timeoutMs, 150);
        expect(found, `${(timeoutMs / 1000).toFixed(1)} sn içinde terminal.${state} gelmedi`);
        since = found.seq;
        return { ev: found, raw, ms: Date.now() - t0 };
      };

      await loginAs(ID4);
      const online = await waitTerminal("online", 5000);
      await check(current.issues, "yük sadece varlık: kimlik, durum, son görülme (gün / check-in / metin yok)", async () => {
        const ev = online.ev;
        expect(ev.day_index === null && ev.payload.day === null, "terminal olayı gün taşıyor");
        expect(JSON.stringify(Object.keys(ev.payload.presence).sort()) === '["astronaut_id","last_seen","state"]', JSON.stringify(ev.payload.presence));
        const extra = Object.entries(ev.payload).filter(([k, v]) => k !== "presence" && v !== null && v !== false);
        expect(extra.length === 0, `yükte başka alan: ${JSON.stringify(Object.fromEntries(extra))}`);
        expect(ev.payload.presence.astronaut_id === ID4 && ev.payload.presence.state === "online", JSON.stringify(ev.payload.presence));
      });
      await check(current.issues, "gizlilik notunda terminal satırı (TR / EN)", async () => {
        const note = checkinCard.locator("[data-presence-note]");
        await note.getByText("Dünya yalnızca terminalinin çevrimiçi olup olmadığını görür; ne yazdığını görmez.", { exact: true }).waitFor({ timeout: 5000 });
        await page.locator(".langseg").getByRole("button", { name: "EN" }).click();
        await page
          .locator("[data-presence-note]")
          .getByText("Earth only sees whether your terminal is online; it does not see what you write.", { exact: true })
          .waitFor({ timeout: 10_000 });
        await page.locator(".langseg").getByRole("button", { name: "TR" }).click();
        await note.getByText(/^Dünya yalnızca terminalinin/).waitFor({ timeout: 10_000 });
      });
      await shot("12-presence-note-1440-light.png");

      // Sayfa açık kaldıkça: zaman aşımından uzun süre geçse de çevrimdışı olmaz (sinyal sürer)
      const before = beats.length;
      const openFor = PRESENCE.timeout * 2 + 1;
      await page.waitForTimeout(openFor * 1000);
      await check(current.issues, `sayfa açıkken ${openFor} sn: sinyal sürer, çevrimdışı olmaz`, async () => {
        const n = beats.length - before;
        expect(n >= PRESENCE.timeout * 2 - 1, `bu sürede sadece ${n} sinyal`);
        const { events } = await downlink(since);
        const mine = events.filter((e) => isTerminalEvent(e) && e.astronaut_id === ID4);
        expect(mine.length === 0, `açıkken terminal olayı: ${mine.map((e) => e.type).join(", ")}`);
        current.notes.push(`açıkken ${openFor} sn: ${n} sinyal (${PRESENCE.heartbeat} sn aralık), olay yok`);
      });

      // "Çıkış": ayrılma sinyali → zaman aşımını beklemeden çevrimdışı
      await page.getByRole("button", { name: "Çıkış" }).click();
      await page.locator("#me-id").waitFor({ timeout: 10_000 });
      const leftOff = await waitTerminal("offline", PRESENCE.timeout * 1000 - 500);
      await check(current.issues, "çıkış: ayrılma sinyali gitti, terminal beklemeden çevrimdışı", async () => {
        expect(beats.some((b) => b.leaving), "çıkışta {leaving: true} gönderilmedi");
        current.notes.push(`çıkış → terminal.offline ${(leftOff.ms / 1000).toFixed(1)} sn (zaman aşımı ${PRESENCE.timeout} sn)`);
      });

      // Sekme kapanır (çıkış yok): son sinyalden zaman aşımı kadar sonra çevrimdışı
      await loginAs(ID4);
      await waitTerminal("online", 5000);
      await page.waitForTimeout(1500);
      await page.close();
      const closedAt = Date.now();
      const lastBeat = beats.filter((b) => !b.leaving).at(-1)?.at ?? closedAt;
      const timedOut = await waitTerminal("offline", (PRESENCE.timeout + PRESENCE.sweep + 5) * 1000);
      await check(current.issues, "sekme kapanınca: zaman aşımıyla çevrimdışı, son görülme = son sinyal", async () => {
        const p = timedOut.ev.payload.presence;
        const gap = (new Date(timedOut.ev.ship_time).getTime() - new Date(p.last_seen).getTime()) / 1000;
        expect(gap >= PRESENCE.timeout, `son sinyalden ${gap.toFixed(1)} sn sonra çevrimdışı (zaman aşımı ${PRESENCE.timeout} sn)`);
        expect(Math.abs(new Date(p.last_seen).getTime() - lastBeat) < 2000, `son görülme ${p.last_seen}, son sinyal ${new Date(lastBeat).toISOString()}`);
        expect(!/Kötü uyudum|Göğsümde|SMOKE-/.test(timedOut.raw), "terminal olaylarının akışında içerik var");
        current.notes.push(`sekme kapandı → terminal.offline ${((Date.now() - closedAt) / 1000).toFixed(1)} sn (son sinyalden ${gap.toFixed(1)} sn)`);
      });
    });
  } catch (e) {
    results.push({ name: "hazırlık", files: [], issues: [{ kind: "check", text: (e as Error).message }], notes: [], ms: 0 });
  } finally {
    await browser?.close();
    await stopTempShip(tempShip);
    // Geride sadece ekran görüntüleri ve log kalsın: geçici veritabanı ve derleme (geçici klasör) silinir
    await warnIfTempLeft();
    if (listeningPids(TEMP_PORT).length > 0) console.error(`${c.yellow}geçici gemi hâlâ ${TEMP_PORT} portunda; kapatın: npm run stop -- --port ${TEMP_PORT}${c.off}`);
  }

  // ------------------------------------------------------------------ rapor
  console.log(`\n${c.bold}Smoke raporu — astronot ekranı${c.off}  ${c.dim}(${TEMP_API}/me: derlenmiş arayüz + geçici gemi; görüntüler: ${OUT})${c.off}\n`);
  let failed = 0;
  for (const r of results) {
    const ok = r.issues.length === 0;
    if (!ok) failed++;
    console.log(`${ok ? `${c.green}✔` : `${c.red}✖`} ${r.name}${c.off} ${c.dim}${(r.ms / 1000).toFixed(1)} sn · ${r.files.length} görüntü${c.off}`);
    for (const n of r.notes) console.log(`    ${c.dim}not: ${n}${c.off}`);
    for (const i of r.issues) console.log(`    ${c.red}${i.kind}${c.off}: ${i.text}`);
  }
  console.log(failed ? `\n${c.red}${failed} adımda sorun var.${c.off}` : `\n${c.green}Tüm adımlar temiz.${c.off}`);
  return failed ? 1 : 0;
}
