#!/usr/bin/env node
/**
 * npm run setup — tek komutla geliştirme ortamı:
 *   1) araç kontrolü (Node, uv)
 *   2) backend: .venv + `uv pip install -e ".[dev]"`
 *   3) .env.example → .env (yoksa; backend ve frontend)
 *   4) kök ve frontend npm bağımlılıkları
 *   5) OpenAPI export + frontend `gen:api`
 *   6) DB boşsa `seed --seed 42`
 * Tekrar çalıştırmak güvenlidir (idempotent). Sistem geneline hiçbir şey kurmaz.
 */
import { spawnSync } from "node:child_process";
import { copyFileSync, existsSync } from "node:fs";
import { join } from "node:path";

import { BACKEND, ROOT, VENV_PYTHON } from "./py.mjs";

const FRONTEND = join(ROOT, "frontend");
const isWin = process.platform === "win32";
const c = { dim: "\x1b[2m", bold: "\x1b[1m", green: "\x1b[32m", yellow: "\x1b[33m", red: "\x1b[31m", off: "\x1b[0m" };

function step(msg) {
  console.log(`\n${c.bold}▶ ${msg}${c.off}`);
}

function fail(msg) {
  console.error(`\n${c.red}${c.bold}✖ ${msg}${c.off}\n`);
  process.exit(1);
}

/** Komutu çalıştır; hata olursa çık. npm/npx Windows'ta .cmd olduğu için shell gerekir. */
function run(cmd, args, { cwd = ROOT, shell = false, allowFail = false, env = {} } = {}) {
  console.log(`${c.dim}$ ${cmd} ${args.join(" ")}  (${cwd})${c.off}`);
  const r = spawnSync(cmd, args, { cwd, stdio: "inherit", shell, env: { ...process.env, PYTHONIOENCODING: "utf-8", ...env } });
  if (r.error) {
    if (allowFail) return r;
    fail(`${cmd} çalıştırılamadı: ${r.error.message}`);
  }
  if (r.status !== 0 && !allowFail) fail(`${cmd} ${args.join(" ")} başarısız (çıkış kodu ${r.status})`);
  return r;
}

const npm = (args, cwd) => run("npm", args, { cwd, shell: isWin });
const py = (args, opts = {}) => run(VENV_PYTHON, args, { cwd: BACKEND, ...opts });

// ---------------------------------------------------------------- 1) araçlar
step("Araçlar kontrol ediliyor");
const [major, minor] = process.versions.node.split(".").map(Number);
if (major < 20 || (major === 20 && minor < 19) || (major === 22 && minor < 12)) {
  fail(`Node ${process.versions.node} çok eski. Vite 8 için Node 20.19+ veya 22.12+ gerekir: https://nodejs.org`);
}
console.log(`Node ${process.versions.node} ✓`);

const uv = spawnSync("uv", ["--version"], { encoding: "utf-8" });
if (uv.error || uv.status !== 0) {
  fail(
    [
      "uv bulunamadı. uv, Python ortamını kuran hızlı paket yöneticisidir (kullanıcı dizinine kurulur).",
      "",
      "  Windows (PowerShell):  winget install --id=astral-sh.uv -e",
      '                     veya powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"',
      "  macOS / Linux:         curl -LsSf https://astral.sh/uv/install.sh | sh",
      "",
      "Kurduktan sonra terminali yeniden açıp tekrar: npm run setup",
      "Ayrıntı: https://docs.astral.sh/uv/getting-started/installation/",
    ].join("\n"),
  );
}
console.log(`${uv.stdout.trim()} ✓`);

// ---------------------------------------------------------------- 2) backend
step("Backend Python ortamı (backend/.venv)");
if (!existsSync(VENV_PYTHON)) {
  run("uv", ["venv", ".venv", "--python", ">=3.11"], { cwd: BACKEND });
} else {
  console.log(`${c.dim}.venv zaten var${c.off}`);
}
run("uv", ["pip", "install", "--python", VENV_PYTHON, "-e", ".[dev]"], { cwd: BACKEND });

// ---------------------------------------------------------------- 3) .env
step(".env dosyaları");
for (const dir of [BACKEND, FRONTEND]) {
  const target = join(dir, ".env");
  if (existsSync(target)) {
    console.log(`${c.dim}${target} zaten var (dokunulmadı)${c.off}`);
  } else {
    copyFileSync(join(dir, ".env.example"), target);
    console.log(`${c.green}${target} oluşturuldu (.env.example'dan)${c.off}`);
  }
}

// ---------------------------------------------------------------- 4) npm
step("npm bağımlılıkları (kök + frontend)");
npm(["install", "--no-fund", "--no-audit"], ROOT);
npm(["install", "--no-fund", "--no-audit"], FRONTEND);

// Görsel smoke testi (npm run smoke) için Playwright tarayıcısı; kullanıcı dizinine iner.
// İndirme başarısız olsa da kurulum devam eder (uygulama tarayıcısız çalışır).
step("Playwright Chromium (npm run smoke için)");
const pw = run("npx", ["playwright", "install", "chromium"], { cwd: FRONTEND, shell: isWin, allowFail: true });
if (pw.error || pw.status !== 0) {
  console.log(`${c.yellow}Chromium indirilemedi; smoke'tan önce elle: cd frontend && npx playwright install chromium${c.off}`);
}

// ---------------------------------------------------------------- 5) sözleşme
step("API sözleşmesi → frontend tipleri");
py(["-m", "app.cli", "export-openapi"]);
npm(["run", "gen:api"], FRONTEND);

// ---------------------------------------------------------------- 6) veri
step("Veritabanı (eski ekranlar için sentetik veri; gemi DB'si ilk açılışta veri setinden kendiliğinden dolar)");
const hasData = py(
  ["-c", "import sys; from app.db import init_db; from app.services.health import check_db; init_db(); sys.exit(0 if check_db().measurements else 3)"],
  { allowFail: true, env: { DATA_SOURCE: "synthetic" } },
);
if (hasData.status === 0) {
  console.log(`${c.dim}DB'de veri var, seed atlandı (sıfırlamak için: npm run seed)${c.off}`);
} else {
  py(["-m", "app.cli", "seed", "--seed", "42"]);
}

console.log(`
${c.green}${c.bold}✔ Kurulum tamam.${c.off}

  ${c.bold}npm run dev:ship${c.off}    gemi: API http://127.0.0.1:8000/docs · astronot ekranı http://localhost:5173/me
  ${c.bold}npm run dev:earth${c.off}   Dünya üssü: API :8001 · http://localhost:5174/monitor (gemiden downlink alır)
  ${c.bold}npm run serve${c.off}       gerçek kurulum (3 bilgisayar): README → "3 bilgisayar kurulumu"
  ${c.bold}npm run dev${c.off}         eski ekranlar (sentetik veri): http://localhost:5173/legacy

  LLM varsayılan olarak mock modda. Gerçek model için backend/.env → LLM_PROVIDER=openai, LLM_BASE_URL=...
`);
