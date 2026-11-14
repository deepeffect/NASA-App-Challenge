/**
 * Görsel smoke testi (Playwright, headless Chromium).
 *
 * Ön koşul: backend (127.0.0.1:8000) ve Vite (localhost:5173) açık → kökte `npm run dev`.
 * Çalıştır:  npm run smoke   (kökte veya frontend/ içinde)
 *
 * Ekranları sırayla açar, tam sayfa ekran görüntülerini frontend/screenshots/ altına yazar ve
 * konsol hatalarını, yakalanmamış JS hatalarını, başarısız/4xx-5xx istekleri raporlar.
 * "Örnek dedektörler" ekranı için 8001 portunda örnek dedektörleri açık ikinci bir backend başlatır
 * ve sadece o ekranın API isteklerini oraya yönlendirir (çalışan dev sunucusuna dokunmaz).
 *
 * Ortam değişkenleri: SMOKE_WEB, SMOKE_API, SMOKE_ML_PORT
 * Çıkış kodu: 0 temiz · 1 hata bulundu · 2 sunucular açık değil
 */
import { type ChildProcess, spawn } from "node:child_process";
import { existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { type Browser, chromium, type Page } from "playwright";

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), "..");
const BACKEND = join(FRONTEND, "..", "backend");
const OUT = join(FRONTEND, "screenshots");
const WEB = (process.env.SMOKE_WEB ?? "http://localhost:5173").replace(/\/$/, "");
const API = (process.env.SMOKE_API ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const ASSISTANT_TIMEOUT = 180_000; // harici asistan API cevabı (yerel model)
const ML_PORT = Number(process.env.SMOKE_ML_PORT ?? 8001);
const ML_API = `http://127.0.0.1:${ML_PORT}`;
const VENV_PY = process.platform === "win32"
  ? join(BACKEND, ".venv", "Scripts", "python.exe")
  : join(BACKEND, ".venv", "bin", "python");
const EXAMPLE_DETECTORS = "threshold,baseline_deviation,trend,example_changepoint,example_forecast,system_pattern";

type IssueKind = "console.error" | "pageerror" | "http" | "requestfailed" | "check";
interface Issue { kind: IssueKind; text: string }
interface ScreenResult { name: string; files: string[]; issues: Issue[]; warnings: string[]; ms: number }

const c = { red: "\x1b[31m", green: "\x1b[32m", yellow: "\x1b[33m", dim: "\x1b[2m", bold: "\x1b[1m", off: "\x1b[0m" };

// ----------------------------------------------------------------------------- yardımcılar
async function reachable(url: string): Promise<boolean> {
  try {
    // /api/health LLM erişimini LLM_HEALTH_TIMEOUT (5 sn) kadar dener → 3 sn yetmez
    const r = await fetch(url, { signal: AbortSignal.timeout(8000) });
    return r.ok;
  } catch {
    return false;
  }
}

async function waitFor(url: string, timeoutMs: number): Promise<boolean> {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    if (await reachable(url)) return true;
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

async function startMlBackend(): Promise<ChildProcess | null> {
  if (await reachable(`${ML_API}/api/health`)) {
    console.log(`${c.dim}${ML_API} zaten açık; örnek dedektörlerin açık olduğu varsayılıyor${c.off}`);
    return null;
  }
  if (!existsSync(VENV_PY)) throw new Error(`${VENV_PY} yok — önce kökte: npm run setup`);
  const child = spawn(VENV_PY, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(ML_PORT)], {
    cwd: BACKEND,
    env: { ...process.env, ANALYSIS_DETECTORS: EXAMPLE_DETECTORS, PYTHONIOENCODING: "utf-8" },
    stdio: "ignore",
  });
  if (!(await waitFor(`${ML_API}/api/health`, 30_000))) {
    child.kill();
    throw new Error(`Örnek dedektörlü backend ${ML_API} açılamadı`);
  }
  return child;
}

/** Sayfaya dinleyiciler bağla; sorunlar `issues`e, uyarılar `warnings`e yazılır. */
function instrument(page: Page, issues: Issue[], warnings: string[]): void {
  page.on("console", (m) => {
    if (m.type() === "error") issues.push({ kind: "console.error", text: m.text() });
    else if (m.type() === "warning") warnings.push(m.text());
  });
  page.on("pageerror", (e) => issues.push({ kind: "pageerror", text: e.message }));
  page.on("requestfailed", (r) => {
    const err = r.failure()?.errorText ?? "";
    if (!err.includes("ERR_ABORTED")) issues.push({ kind: "requestfailed", text: `${r.method()} ${r.url()} — ${err}` });
  });
  page.on("response", (r) => {
    if (r.status() >= 400) issues.push({ kind: "http", text: `${r.status()} ${r.request().method()} ${r.url()}` });
  });
}

/** Yükleniyor göstergeleri kaybolana ve ağ sakinleşene kadar bekle. */
async function settle(page: Page): Promise<void> {
  // Not: Recharts tooltip'i de role="status" taşır; bu yüzden kendi Spinner'ımızın işaretine bakıyoruz
  await page.waitForFunction(() => !document.querySelector("[data-spinner]"), null, { timeout: 15_000 });
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(400); // grafik animasyonları/yerleşim
}

async function expectText(page: Page, issues: Issue[], text: string | RegExp, what: string): Promise<void> {
  try {
    await page.getByText(text).first().waitFor({ timeout: 10_000 });
  } catch {
    issues.push({ kind: "check", text: `beklenen içerik bulunamadı: ${what} (${text})` });
  }
}

// ----------------------------------------------------------------------------- ekranlar
interface Ctx { page: Page; issues: Issue[]; shot: (file: string, selector?: string) => Promise<void>; dates: Record<string, string> }
type Screen = { name: string; ml?: boolean; viewport?: { width: number; height: number }; run: (x: Ctx) => Promise<void> };

const screens: Screen[] = [
  {
    name: "1. Mürettebat ekranı",
    run: async ({ page, issues, shot }) => {
      await page.goto(`${WEB}/`);
      await page.getByRole("heading", { name: "Crew" }).waitFor();
      await page.getByRole("link", { name: /^Open .* details$/ }).nth(3).waitFor();
      await settle(page);
      await expectText(page, issues, "Critical", "AST-02 kırmızı durum metni");
      await shot("01-crew.png");
    },
  },
  {
    name: "2. AST-02 detayı — 150. gün (yeşil)",
    run: async ({ page, issues, shot, dates }) => {
      await page.goto(`${WEB}/astronauts/AST-02?as_of=${dates.d150}`);
      await page.getByRole("heading", { name: "Astronaut 2" }).waitFor();
      await settle(page);
      await expectText(page, issues, /Mission day 150\b/, "başlıkta görev günü 150");
      await expectText(page, issues, "No active alerts", "olay listesi boş");
      await shot("02-ast02-day150.png");
    },
  },
  {
    name: "3. AST-02 detayı — 157. gün (kırmızı), olay kartı açık",
    run: async ({ page, issues, shot, dates }) => {
      await page.goto(`${WEB}/astronauts/AST-02?as_of=${dates.d157}`);
      await page.getByRole("heading", { name: "Astronaut 2" }).waitFor();
      await settle(page);
      await page.getByRole("button", { name: "Why?" }).first().click();
      await expectText(page, issues, "Possible factors", "açıklama paneli");
      await settle(page);
      await shot("03-ast02-day157.png");
      await shot("03b-event-card.png", "article");
    },
  },
  {
    name: "4. Metrik grafiği — örnek dedektörler açık",
    ml: true,
    run: async ({ page, issues, shot }) => {
      await page.goto(`${WEB}/astronauts/AST-02`);
      await page.getByRole("heading", { name: "Astronaut 2" }).waitFor();
      await page.getByLabel("Select metric").selectOption("sleep_duration");
      await page.getByLabel("Day range").selectOption("60");
      await settle(page);
      const panel = page.locator("#metric-panel");
      await panel.scrollIntoViewIfNeeded();
      for (const [txt, what] of [["Personal normal", "baseline bandı"], ["Change point", "changepoint"], ["Forecast", "forecast"]]) {
        if (!(await panel.getByText(txt).count())) issues.push({ kind: "check", text: `grafikte katman yok: ${what}` });
      }
      await shot("04-metric-chart.png", "#metric-panel");
      await shot("04b-ast02-with-ml.png");
    },
  },
  {
    // Sohbet harici asistan API'sine gider (VITE_ASSISTANT_API_URL); yerel model 10–30 sn sürebilir.
    name: "5. Sohbet paneli (asistan API)",
    run: async ({ page, issues, shot }) => {
      await page.goto(`${WEB}/astronauts/AST-02`);
      await page.getByRole("heading", { name: "Astronaut 2" }).waitFor();
      await settle(page);
      const input = page.locator("#chat-input");
      await input.fill("How is my sleep?");
      await input.press("Enter");
      await page.locator("#chat-input:enabled").waitFor({ timeout: ASSISTANT_TIMEOUT });
      const chatErr = page.locator("section", { has: page.getByRole("heading", { name: "Health assistant" }) }).getByText(/^Error:/);
      if (await chatErr.count()) issues.push({ kind: "check", text: `asistan cevabı yok: ${await chatErr.first().innerText()}` });
      const chat = page.locator("section", { has: page.getByRole("heading", { name: "Health assistant" }) });
      await chat.scrollIntoViewIfNeeded();
      await shot("05-chat.png", 'section:has(h2:text("Health assistant"))');
      await input.fill("I feel pressure in my chest and shortness of breath");
      await input.press("Enter");
      await expectText(page, issues, /EMERGENCY:/, "acil durum bandı");
      await page.locator("#chat-input:enabled").waitFor({ timeout: ASSISTANT_TIMEOUT });
      await shot("05b-chat-emergency.png", 'section:has(h2:text("Health assistant"))');
    },
  },
  {
    name: "6. Check-in formu",
    run: async ({ page, shot }) => {
      await page.goto(`${WEB}/checkin/AST-01`);
      await page.getByRole("heading", { name: "Daily check-in" }).waitFor();
      await settle(page);
      await page.getByRole("group", { name: "Your mood" }).getByText("4", { exact: true }).click();
      await page.getByRole("group", { name: "Your stress level" }).getByText("2", { exact: true }).click();
      await page.locator("#note").fill("We stayed on the experiment plan today, a bit tired.");
      await shot("06-checkin.png");
    },
  },
  {
    name: "7. Mürettebat — telefon genişliği (390 px)",
    viewport: { width: 390, height: 844 },
    run: async ({ page, shot }) => {
      await page.goto(`${WEB}/`);
      await page.getByRole("link", { name: /^Open .* details$/ }).nth(3).waitFor();
      await settle(page);
      await shot("07-crew-mobile.png");
    },
  },
];

// ----------------------------------------------------------------------------- ana akış
async function main(): Promise<number> {
  if (!(await reachable(`${API}/api/health`)) || !(await reachable(WEB))) {
    console.error(`${c.red}Backend (${API}) veya Vite (${WEB}) açık değil. Önce kökte: npm run dev${c.off}`);
    return 2;
  }
  const crew = (await (await fetch(`${API}/api/crew`)).json()) as { mission: { start_date: string; latest_date: string } };
  const start = crew.mission.start_date;
  const dates = { d150: addDays(start, 149), d157: addDays(start, 156), latest: crew.mission.latest_date };

  rmSync(OUT, { recursive: true, force: true });
  mkdirSync(OUT, { recursive: true });

  let ml: ChildProcess | null = null;
  let browser: Browser | null = null;
  const results: ScreenResult[] = [];
  try {
    ml = await startMlBackend();
    browser = await chromium.launch();
    for (const s of screens) {
      const t0 = Date.now();
      const issues: Issue[] = [];
      const warnings: string[] = [];
      const files: string[] = [];
      const context = await browser.newContext({
        viewport: s.viewport ?? { width: 1440, height: 900 },
        locale: "tr-TR",
        timezoneId: "UTC",
        colorScheme: "dark",
      });
      const page = await context.newPage();
      instrument(page, issues, warnings);
      if (s.ml) {
        await page.route(`${API}/**`, (route) => route.continue({ url: route.request().url().replace(API, ML_API) }));
      }
      const shot = async (file: string, selector?: string) => {
        const path = join(OUT, file);
        // Sabit header kaydırılmış sayfada içeriğin üstüne biner; görüntü için akışa al (yerleşim değişmez)
        await page.addStyleTag({ content: "header { position: static !important; }" });
        if (selector) await page.locator(selector).first().screenshot({ path });
        else await page.screenshot({ path, fullPage: true });
        files.push(file);
      };
      try {
        await s.run({ page, issues, shot, dates });
      } catch (e) {
        issues.push({ kind: "check", text: `adım başarısız: ${(e as Error).message.split("\n")[0]}` });
        await page.screenshot({ path: join(OUT, `FAIL-${files.length}-${s.name.slice(0, 2)}.png`), fullPage: true }).catch(() => undefined);
      }
      results.push({ name: s.name, files, issues, warnings, ms: Date.now() - t0 });
      await context.close();
    }
  } finally {
    await browser?.close();
    ml?.kill();
  }

  // ------------------------------------------------------------------ rapor
  console.log(`\n${c.bold}Smoke raporu${c.off}  ${c.dim}(${WEB} → ${API}; görüntüler: ${OUT})${c.off}\n`);
  let failed = 0;
  for (const r of results) {
    const ok = r.issues.length === 0;
    if (!ok) failed++;
    console.log(`${ok ? `${c.green}✔` : `${c.red}✖`} ${r.name}${c.off} ${c.dim}${(r.ms / 1000).toFixed(1)} sn · ${r.files.join(", ") || "-"}${c.off}`);
    for (const i of r.issues) console.log(`    ${c.red}${i.kind}${c.off}: ${i.text}`);
    const uniqWarn = [...new Set(r.warnings)];
    for (const w of uniqWarn.slice(0, 5)) console.log(`    ${c.yellow}uyarı${c.off}: ${w.slice(0, 200)}`);
  }
  console.log(failed ? `\n${c.red}${failed} ekranda sorun var.${c.off}` : `\n${c.green}Tüm ekranlar temiz.${c.off}`);
  return failed ? 1 : 0;
}

main().then((code) => process.exit(code), (e) => {
  console.error(e);
  process.exit(1);
});
