#!/usr/bin/env node
/**
 * Backend geliştirme sunucusu + kendi auto-reload'umuz.
 *   node scripts/backend-dev.mjs [--host 127.0.0.1] [--port 8000] [--legacy]
 *   --legacy → DATA_SOURCE=synthetic (eski ekranlar ve eski API, DB: data/processed/health.db)
 *
 * Neden uvicorn --reload değil: Windows'ta uvicorn reload ederken worker'a
 * os.kill(pid, CTRL_C_EVENT) gönderir; bu sinyal konsolu paylaşan TÜM süreçlere gider.
 * `npm run dev` altında npm'in .cmd sarmalayıcıları "Terminate batch job (Y/N)?" deyip kapanır ve
 * concurrently frontend'i de kapatır. Burada uvicorn reload'suz çalışır; app/ altındaki .py
 * değişince süreç ağacı konsol sinyali kullanmadan (taskkill /T /F, POSIX'te SIGTERM) yeniden başlatılır.
 */
import { spawn, spawnSync } from "node:child_process";
import { existsSync, watch } from "node:fs";
import { join, relative } from "node:path";

import { BACKEND, VENV_PYTHON } from "./py.mjs";

const args = process.argv.slice(2);
const opt = (name, def) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] ? args[i + 1] : def;
};
const HOST = opt("host", "127.0.0.1");
const PORT = opt("port", "8000");
const LEGACY = args.includes("--legacy");
const WATCH_DIR = join(BACKEND, "app");
const isWin = process.platform === "win32";
const tag = "\x1b[2m[reload]\x1b[0m";

if (!existsSync(VENV_PYTHON)) {
  console.error(`${VENV_PYTHON} bulunamadı. Önce kök klasörde: npm run setup`);
  process.exit(1);
}

let child = null;
let stopping = false;
let restarting = false;
let quickFails = 0;

function start() {
  const startedAt = Date.now();
  child = spawn(VENV_PYTHON, ["-m", "uvicorn", "app.main:app", "--host", HOST, "--port", PORT], {
    cwd: BACKEND,
    stdio: "inherit",
    env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1", ...(LEGACY ? { DATA_SOURCE: "synthetic" } : {}) },
  });
  child.on("exit", (code) => {
    child = null;
    if (stopping) process.exit(0);
    if (restarting) return; // restart() yeni süreci başlatacak
    // Port henüz boşalmadıysa vb. hızlı çöküşte birkaç kez tekrar dene; aksi halde değişiklik bekle
    if (Date.now() - startedAt < 3000 && quickFails < 5) {
      quickFails++;
      setTimeout(start, 600);
    } else {
      console.log(`${tag} backend kapandı (kod ${code ?? "?"}); düzeltip kaydedince yeniden başlar.`);
    }
  });
}

function killTree(proc) {
  if (!proc || proc.exitCode !== null) return Promise.resolve();
  return new Promise((resolve) => {
    proc.once("exit", () => resolve());
    if (isWin) spawnSync("taskkill", ["/pid", String(proc.pid), "/T", "/F"], { stdio: "ignore" });
    else proc.kill("SIGTERM");
    setTimeout(resolve, 5000); // emniyet
  });
}

async function restart(file) {
  if (restarting) return;
  restarting = true;
  console.log(`${tag} değişiklik: ${file} → yeniden başlatılıyor`);
  await killTree(child);
  restarting = false;
  quickFails = 0;
  start();
}

// Art arda gelen olaylar (kaydetme, git checkout, biçimleyici) tek yeniden başlatmada birleşir
const DEBOUNCE_MS = 500;
// Bu klasörlerdeki değişiklikler yok sayılır (önbellek, sanal ortam, veritabanı, bağımlılıklar)
const IGNORED = new Set(["__pycache__", ".venv", "data", "node_modules"]);
const ignored = (file) => file.split(/[\\/]/).some((part) => IGNORED.has(part));

let timer = null;
let pending = "";
watch(WATCH_DIR, { recursive: true }, (_event, filename) => {
  if (!filename || !filename.endsWith(".py") || ignored(filename)) return;
  pending = relative(BACKEND, join(WATCH_DIR, filename));
  clearTimeout(timer);
  timer = setTimeout(() => void restart(pending), DEBOUNCE_MS);
});

for (const sig of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(sig, async () => {
    stopping = true;
    await killTree(child);
    process.exit(0);
  });
}

console.log(`${tag} ${relative(BACKEND, WATCH_DIR)}/ izleniyor (http://${HOST}:${PORT})`);
start();
