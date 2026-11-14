/**
 * Astronot ekranının (/me) smoke testi (Playwright, headless Chromium).
 *
 * Ön koşul: kökte `npm run dev:ship` (web :5173). Çalıştır: `npm run smoke -- personal`.
 *
 * API için test KENDİ geçici gemi backend'ini başlatır (port 8010, boş ve atılabilir bir veritabanı) ve sayfanın
 * API isteklerini oraya yönlendirir. Böylece geliştirme veritabanına (ship.db) dokunulmaz ve senaryo her
 * çalıştırmada baştan tekrarlanabilir (paylaşım geri alınamadığı için bu şart). Geçici backend sonunda kapatılır.
 *
 * Adımlar:
 *   1. Giriş kartı: kimlik aralığı /api/auth/hint'ten; EARTH girişi yok
 *   2. A000 ile giriş → bugünün ekranı (durum, şerit, yapılacaklar, check-in)
 *   3. Şeritte gün seçimi → geçmiş gün salt okunur (check-in yok, "Yaptım" yok); önceki/sonraki; bugüne dönüş
 *   4. "Yaptım" → backend'e yazılır
 *   5. Bugünün check-in'i sonuna kadar → notlar, aktif mod satırı
 *   6. "Sadece skorlar" ile paylaşım → geminin downlink akışında `checkin.shared` olayı ruh hali / stres
 *      skorlarını taşır, cevap METNİNİ taşımaz
 *   7. Ayrıntılar (grafik iki çizgi + ölçümler) ve "tüm öz bakım çözümleri" penceresi
 *   8. Asistana sor (mock) + acil belirti kutusu; sohbet downlink'e girmez
 *   9. Başka bir astronotta check-in'de acil belirti → "Gemideki sağlık sorumlusu bilgilendirildi" kutusu;
 *      bu bilgi downlink'e girmez
 *  10. TR → EN; yenilemede oturum sürer; "Çıkış" token'ı siler
 *
 * Ana durumların ekran görüntüleri 390 ve 1440 px'te, açık ve koyu temada alınır: screenshots/personal/.
 * Ayrıca: konsol hatası, yakalanmamış hata, başarısız istek, 4xx/5xx ve dış ağa istek olmamalı (offline).
 *
 * Ortam değişkenleri: SMOKE_WEB (http://localhost:5173), SMOKE_API (sayfanın derlendiği API adresi,
 * http://127.0.0.1:8000), SMOKE_PERSONAL_PORT (8010), SMOKE_ASTRONAUT (A000)
 * Çıkış kodu: 0 temiz · 1 sorun bulundu · 2 ön koşul yok
 */
import { type ChildProcess, spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, openSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { type Browser, chromium, type Page } from "playwright";

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = join(FRONTEND, "..");
const BACKEND = join(ROOT, "backend");
const OUT = join(FRONTEND, "screenshots", "personal");
const WEB = (process.env.SMOKE_WEB ?? "http://localhost:5173").replace(/\/$/, "");
const DEV_API = (process.env.SMOKE_API ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const TEMP_PORT = Number(process.env.SMOKE_PERSONAL_PORT ?? 8010);
const TEMP_API = `http://127.0.0.1:${TEMP_PORT}`;
const ID = process.env.SMOKE_ASTRONAUT?.trim().toUpperCase() || "A000";
/** Acil belirti (CMO kutusu) adımı için ikinci astronot: ilkinin check-in'i paylaşıldığı için baştan başlatılamaz. */
const ID2 = ID === "A001" ? "A002" : "A001";
const LINK_TOKEN = "smoke-link-token";
const isWin = process.platform === "win32";
const VENV_PY = isWin ? join(BACKEND, ".venv", "Scripts", "python.exe") : join(BACKEND, ".venv", "bin", "python");
const DB_FILE = join(OUT, "ship-smoke.db");

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

function listeningPid(port: number): number | null {
  if (isWin) {
    const r = spawnSync("netstat", ["-ano", "-p", "tcp"], { encoding: "utf-8" });
    for (const line of r.stdout.split(/\r?\n/)) {
      const p = line.trim().split(/\s+/);
      if (p.length >= 5 && p[1].endsWith(`:${port}`) && p[3] === "LISTENING") return Number(p[4]);
    }
    return null;
  }
  const r = spawnSync("lsof", ["-ti", `tcp:${port}`, "-sTCP:LISTEN"], { encoding: "utf-8" });
  const pid = Number(r.stdout.trim().split(/\s+/)[0]);
  return Number.isFinite(pid) && pid > 0 ? pid : null;
}

function killPid(pid: number): void {
  if (isWin) spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
  else process.kill(pid, "SIGTERM");
}

/** Geçici gemi: boş veritabanı (açılışta veri setinden dolar), hazır sorular, mock model, gecikmesiz downlink. */
async function startTempShip(): Promise<ChildProcess> {
  const origin = new URL(WEB).origin;
  const child = spawn(VENV_PY, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(TEMP_PORT)], {
    cwd: BACKEND,
    env: {
      ...process.env,
      STATION_ROLE: "ship",
      DATA_SOURCE: "astronaut_health",
      DATABASE_URL: `sqlite:///${DB_FILE.replaceAll("\\", "/")}`,
      CORS_ORIGINS: [...new Set([origin, "http://localhost:5173", "http://127.0.0.1:5173"])].join(","),
      EARTH_LINK_TOKEN: LINK_TOKEN,
      CHECKIN_MODE: "scripted",
      LLM_PROVIDER: "mock",
      DOWNLINK_DELAY_SECONDS: "0",
      PYTHONIOENCODING: "utf-8",
      PYTHONUTF8: "1",
    },
    stdio: ["ignore", openSync(join(OUT, "ship-smoke.log"), "w"), openSync(join(OUT, "ship-smoke.err.log"), "w")],
  });
  const ready = await waitUntil(async () => {
    const hint = (await (await fetch(`${TEMP_API}/api/auth/hint`, { signal: AbortSignal.timeout(3000) })).json()) as { astronauts: { count: number } | null };
    return (hint.astronauts?.count ?? 0) > 0;
  }, 120_000);
  if (!ready) {
    stopTempShip(child);
    throw new Error(`geçici gemi ${TEMP_API} açılamadı (log: ${join(OUT, "ship-smoke.err.log")})`);
  }
  return child;
}

function stopTempShip(child: ChildProcess | null): void {
  child?.kill();
  const pid = listeningPid(TEMP_PORT); // Windows'ta venv başlatıcısının alt süreci ayakta kalabilir
  if (pid) killPid(pid);
}

function instrument(page: Page, report: (i: Issue) => void): void {
  const allowed = new Set([new URL(WEB).host, new URL(DEV_API).host, new URL(TEMP_API).host]);
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
  if (!(await reachable(`${WEB}/me`))) {
    console.error(`${c.red}Astronot ekranı (${WEB}/me) açık değil. Önce kökte: npm run dev:ship${c.off}`);
    return 2;
  }
  if (!existsSync(VENV_PY)) {
    console.error(`${c.red}${VENV_PY} yok — önce kökte: npm run setup${c.off}`);
    return 2;
  }
  if (listeningPid(TEMP_PORT)) {
    console.error(`${c.red}Port ${TEMP_PORT} dolu (önceki bir smoke'tan kalmış olabilir). Kapatın veya SMOKE_PERSONAL_PORT ile başka port verin.${c.off}`);
    return 2;
  }

  rmSync(OUT, { recursive: true, force: true });
  mkdirSync(OUT, { recursive: true });
  const marker = `SMOKE-${Date.now().toString(36).toUpperCase()}`;
  const results: StepResult[] = [];
  let browser: Browser | null = null;
  let tempShip: ChildProcess | null = null;

  try {
    process.stdout.write(`${c.dim}geçici gemi başlatılıyor (${TEMP_API}, boş veritabanı)…${c.off}\n`);
    tempShip = await startTempShip();

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
    // Sayfa dev API adresiyle derlenmiştir; istekleri geçici gemiye çevir (dev veritabanına dokunma).
    await page.route(`${DEV_API}/**`, (route) => route.continue({ url: route.request().url().replace(DEV_API, TEMP_API) }));

    let current: StepResult = { name: "", files: [], issues: [], notes: [], ms: 0 };
    instrument(page, (i) => current.issues.push(i));

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
    const loginAs = async (id: string) => {
      await page.locator("#me-id").fill(id);
      await page.locator("#me-pw").fill(id);
      await page.getByRole("button", { name: "Giriş yap" }).click();
      await strip.getByRole("button").nth(29).waitFor({ timeout: 20_000 });
      await page.locator(".todo h2").waitFor({ timeout: 10_000 });
    };

    // ------------------------------------------------------------------ 1
    await step("1. Giriş kartı (kimlik aralığı API'den, EARTH girişi yok)", async () => {
      await page.goto(`${WEB}/me`);
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
    await step("3. Şeritte gün seçimi → geçmiş gün salt okunur; önceki/sonraki; bugüne dönüş", async () => {
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
        const { events, raw } = await downlink(before);
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
  } catch (e) {
    results.push({ name: "hazırlık", files: [], issues: [{ kind: "check", text: (e as Error).message }], notes: [], ms: 0 });
  } finally {
    await browser?.close();
    stopTempShip(tempShip);
    await sleep(500);
    rmSync(DB_FILE, { force: true });
    for (const ext of ["-wal", "-shm"]) rmSync(DB_FILE + ext, { force: true });
  }

  // ------------------------------------------------------------------ rapor
  console.log(`\n${c.bold}Smoke raporu — astronot ekranı${c.off}  ${c.dim}(${WEB}/me → geçici gemi ${TEMP_API}; görüntüler: ${OUT})${c.off}\n`);
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
