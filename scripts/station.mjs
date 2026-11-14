#!/usr/bin/env node
/**
 * İstasyon rolleri için geliştirme komutları (aynı makinede iki rol yan yana çalışabilir).
 *
 *   node scripts/station.mjs dev ship     # npm run dev:ship  → API :8000 (ship.db)  + web :5173
 *   node scripts/station.mjs dev earth    # npm run dev:earth → API :8001 (earth.db) + web :5174,
 *                                          #                     SHIP_URL=http://127.0.0.1:8000
 *   node scripts/station.mjs reset [ship|earth]
 *        Rol verilirse dev:<rol> ile aynı DB'yi sıfırlar. Rol verilmezse STATION_ROLE (ortam veya
 *        backend/.env, yoksa ship) ve backend/.env ayarları kullanılır (gerçek kurulum makinesi).
 *
 *   node scripts/station.mjs serve [ship|earth] [--port 8000] [--no-build]
 *        npm run serve → frontend'i derler (aynı adres: VITE_API_BASE_URL boş) ve backend'i 0.0.0.0:8000'de
 *        başlatır; backend derlenmiş arayüzü kendisi servis eder (gemi /me, Dünya /monitor). Rol ve diğer
 *        ayarlar backend/.env'den (rol argümanı STATION_ROLE'ü ezer). 3 bilgisayar kurulumu: README.
 *
 *   node scripts/station.mjs stop [ship|earth] [--port N] [--force]
 *        npm run stop → rolün portlarını (API + web) dinleyen süreç ağaçlarını kapatır; rol verilmezse iki rolünkini.
 *        Windows'ta `taskkill /PID <pid> /T /F`. Sadece BU depoya ait süreçler kapatılır; portu başka bir program
 *        tutuyorsa dokunulmaz (`--force` ile o da kapatılır). `--port N` → o portu da (rol yoksa sadece onu) kapat.
 *        Neden var: bug_read.md — üst süreç zorla sonlandırılınca uvicorn ve Vite sahipsiz kalıp portları tutar.
 *
 *   node scripts/station.mjs check [ship|earth]
 *        Rolün portları boş mu? Doluysa kimin tuttuğunu yazar ve 1 ile çıkar (npm run dev bunu önce çalıştırır).
 *
 * dev ve serve başlamadan önce portlarına bakar; doluysa hangi sürecin tuttuğunu söyler ve `npm run stop` önerir.
 *
 * Seçenekler: --lan → API'yi 0.0.0.0'da dinlet (ağdaki diğer makineler bağlanabilsin).
 * Geliştirmede iki rol aynı EARTH_LINK_TOKEN'ı kullanır (ortamda yoksa "dev-link-token").
 */
import { spawn, spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { networkInterfaces } from "node:os";
import { join } from "node:path";

import concurrently from "concurrently";

import { descendantsOf, killTree, listeningPids, listProcesses } from "./ports.mjs";
import { BACKEND, ROOT, VENV_PYTHON } from "./py.mjs";

export const ROLES = {
  ship: { api: 8000, web: 5173, db: "ship.db" },
  earth: { api: 8001, web: 5174, db: "earth.db" },
};

const sqliteUrl = (file) => `sqlite:///${join(ROOT, "data", "processed", file).replaceAll("\\", "/")}`;

/** dev:<rol> için backend ortamı. */
export function devBackendEnv(role) {
  const r = ROLES[role];
  const env = {
    STATION_ROLE: role,
    DATA_SOURCE: "astronaut_health",
    DATABASE_URL: sqliteUrl(r.db),
    CORS_ORIGINS: `http://localhost:${r.web},http://127.0.0.1:${r.web}`,
    EARTH_LINK_TOKEN: process.env.EARTH_LINK_TOKEN ?? "dev-link-token",
  };
  if (role === "earth") env.SHIP_URL = process.env.SHIP_URL ?? `http://127.0.0.1:${ROLES.ship.api}`;
  return env;
}

/** backend/.env içinden tek bir anahtarı okur (basit KEY=VALUE; yorum ve tırnak desteği). */
export function readBackendEnv(key) {
  const file = join(BACKEND, ".env");
  if (!existsSync(file)) return undefined;
  for (const raw of readFileSync(file, "utf-8").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const i = line.indexOf("=");
    if (i < 0 || line.slice(0, i).trim() !== key) continue;
    return line.slice(i + 1).trim().replace(/^["']|["']$/g, "");
  }
  return undefined;
}

function parseRole(value, fallback) {
  const role = (value ?? fallback ?? "").toLowerCase();
  if (!ROLES[role]) {
    console.error(`Bilinmeyen rol: "${value}". Geçerli roller: ${Object.keys(ROLES).join(", ")}`);
    process.exit(2);
  }
  return role;
}

// ---------------------------------------------------------------- artakalan süreçler (bug_read.md)
const norm = (s) => s.replaceAll("\\", "/").toLowerCase();

/** Komut satırında deponun yolu geçiyor mu (uvicorn: backend/.venv altından, Vite: frontend/node_modules altından çalışır). */
const mentionsRepo = (p) => p.command !== "" && norm(p.command).includes(norm(ROOT));

/** Bu projenin geliştirme zincirinin bir halkası: npm run dev… → station.mjs → backend-dev.mjs → uvicorn / vite. */
const DEV_CHAIN =
  /scripts[\\/]backend-dev\.mjs|scripts[\\/]station\.mjs["']?\s+(dev|serve)\b|\bconcurrently\b|\brun\s+(dev(:[\w-]+)?|serve)\b|[\\/]vite[\\/]bin[\\/]vite\.js|\bvite\s+--port\b|uvicorn\s+app\.main:app/i;

const describe = (p) => `pid ${p.pid} ${p.name || "(adı okunamadı)"}`;
const short = (cmd) => (cmd.length > 170 ? `${cmd.slice(0, 167)}…` : cmd);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * Verilen portları tutan süreçleri ve rollerin geliştirme zincirinden artakalanları bulur.
 *   holders  portu dinleyen süreçler ({ port, …süreç, ours })
 *   foreign  portu tutan ama bu depoya ait görünmeyen süreçler (komut satırında deponun yolu yok)
 *   roots    kapatılacak süreç ağaçlarının tepeleri: dinleyen süreçten yukarı, zincirin en üst halkasına kadar çıkılır
 *            (yoksa `backend-dev.mjs` hayatta kalır ve app/ altında bir .py değişince uvicorn'u yeniden başlatır).
 *            Port dinlemeyen artık zincirler de (sunucusu kapanmış ama izleyicisi yaşayan) buraya girer.
 * Bu komutu çalıştıran süreç ve onun üst süreçleri hiçbir zaman hedef olmaz.
 */
function findLeftovers(ports, roles) {
  const procs = listProcesses();
  const byPid = new Map(procs.map((p) => [p.pid, p]));
  const self = new Set([process.pid]);
  for (let p = byPid.get(process.pid), i = 0; p && i < 20; p = byPid.get(p.ppid), i++) self.add(p.pid);

  const parentOf = (p) => {
    const parent = byPid.get(p.ppid);
    if (!parent || self.has(parent.pid)) return undefined;
    if (parent.started && p.started && parent.started > p.started + 2000) return undefined; // PID yeniden kullanılmış
    return parent;
  };
  const topOf = (p) => {
    let top = p;
    for (let i = 0; i < 20; i++) {
      const parent = parentOf(top);
      if (!parent || !(DEV_CHAIN.test(parent.command) || mentionsRepo(parent))) break;
      top = parent;
    }
    return top;
  };

  const holders = [];
  const foreign = [];
  const roots = new Map();
  const addRoot = (p) => {
    const top = topOf(p);
    roots.set(top.pid, top);
  };
  for (const port of ports) {
    for (const pid of listeningPids(port)) {
      const p = byPid.get(pid) ?? { pid, ppid: 0, name: "", command: "", started: 0 };
      const ours = mentionsRepo(p);
      holders.push({ port, ...p, ours });
      if (ours) addRoot(p);
      else foreign.push({ port, ...p });
    }
  }
  const apiPorts = roles.map((r) => ROLES[r].api);
  const webPorts = roles.map((r) => ROLES[r].web);
  const hasPort = (p, list) => list.some((n) => new RegExp(`--port\\s+${n}\\b`).test(p.command));
  for (const p of procs) {
    if (self.has(p.pid)) continue;
    const watcher = /scripts[\\/]backend-dev\.mjs/.test(p.command) && hasPort(p, apiPorts);
    const station = roles.some((r) => new RegExp(`scripts[\\\\/]station\\.mjs["']?\\s+dev\\s+${r}\\b`).test(p.command));
    const vite = mentionsRepo(p) && /vite/i.test(p.command) && hasPort(p, webPorts);
    if (watcher || station || vite) addRoot(p);
  }
  const all = [...roots.values()];
  const inside = new Set(all.flatMap((r) => descendantsOf(r.pid, procs).map((d) => d.pid)));
  return { procs, holders, foreign, roots: all.filter((r) => !inside.has(r.pid)) };
}

/**
 * Başlamadan önce: portlar doluysa veya eski bir geliştirme oturumu hâlâ açıksa kimin tuttuğunu yazar,
 * `npm run stop` önerir ve 1 ile çıkar. Temizse sessizce döner.
 */
function ensureClear(ports, roles, stopArgs) {
  const { procs, holders, roots } = findLeftovers(ports, roles);
  if (holders.length === 0 && roots.length === 0) return;
  console.error("");
  for (const h of holders) {
    console.error(`✖ Port ${h.port} dolu: ${describe(h)}${h.ours ? "" : "  (bu depoya ait görünmüyor)"}`);
    if (h.command) console.error(`    ${short(h.command)}`);
  }
  const holderPids = new Set(holders.map((h) => h.pid));
  for (const r of roots) {
    if (holderPids.has(r.pid) || descendantsOf(r.pid, procs).some((d) => holderPids.has(d.pid))) continue;
    console.error(`✖ Eski bir geliştirme oturumu hâlâ açık (şu an port dinlemiyor): ${describe(r)}`);
    if (r.command) console.error(`    ${short(r.command)}`);
  }
  const cmd = `npm run stop${stopArgs ? ` -- ${stopArgs}` : ""}`;
  console.error("");
  console.error(`Başlatılmadı. Önce kapatın:  ${cmd}`);
  if (holders.some((h) => !h.ours)) {
    console.error(`Bu depoya ait olmayan süreci kendiniz kapatın ya da:  ${cmd}${stopArgs ? "" : " --"} --force`);
  }
  console.error("(Zorla durdurulmuş bir geliştirme sunucusundan kalmış olabilir: bug_read.md)");
  console.error("");
  process.exit(1);
}

/**
 * npm run stop: rollerin portlarını tutan ve rollerin geliştirme zincirinden artakalan süreç ağaçlarını kapatır.
 * Portu bu depoya ait olmayan bir program tutuyorsa dokunmaz (`--force` ile onu da kapatır).
 */
async function stop(roleArg, { extraPort, force }) {
  const roles = roleArg !== undefined ? [parseRole(roleArg)] : extraPort !== undefined ? [] : Object.keys(ROLES);
  const ports = [...new Set([...roles.flatMap((r) => [ROLES[r].api, ROLES[r].web]), ...(extraPort !== undefined ? [extraPort] : [])])];
  const closed = new Set();
  let skipped = [];
  // Birkaç tur: bir ağaç kapanırken başka bir artık izleyici sunucuyu yeniden başlatmış olabilir
  for (let round = 0; round < 4; round++) {
    const { procs, foreign, roots } = findLeftovers(ports, roles);
    skipped = force ? [] : foreign;
    const targets = [...roots, ...(force ? foreign : [])].filter((t, i, all) => all.findIndex((x) => x.pid === t.pid) === i);
    if (targets.length === 0) break;
    for (const t of targets) {
      if (!closed.has(t.pid)) {
        const n = descendantsOf(t.pid, procs).length;
        console.log(`kapatılıyor: ${describe(t)}${n ? ` + ${n} alt süreç` : ""}`);
        if (t.command) console.log(`    ${short(t.command)}`);
      }
      closed.add(t.pid);
      killTree(t.pid, procs);
    }
    await sleep(900);
  }
  for (const h of skipped) {
    console.error(`port ${h.port}: ${describe(h)} bu depoya ait görünmüyor, KAPATILMADI (kapatmak için: --force)`);
    if (h.command) console.error(`    ${short(h.command)}`);
  }
  const still = ports.filter((p) => listeningPids(p).length > 0);
  const free = ports.filter((p) => !still.includes(p));
  if (closed.size > 0) console.log(`✔ ${closed.size} süreç ağacı kapatıldı${free.length ? `; boş portlar: ${free.join(", ")}` : ""}`);
  else if (still.length === 0) console.log(`Kapatılacak süreç yok; portlar boş: ${ports.join(", ")}`);
  if (still.length) {
    console.error(`✖ Hâlâ dolu: ${still.join(", ")}`);
    process.exit(1);
  }
}

function requireVenv() {
  if (!existsSync(VENV_PYTHON)) {
    console.error(`${VENV_PYTHON} bulunamadı. Önce kök klasörde: npm run setup`);
    process.exit(1);
  }
}

function dev(role, { lan }) {
  requireVenv();
  const r = ROLES[role];
  ensureClear([r.api, r.web], [role], role);
  const host = lan ? "0.0.0.0" : "127.0.0.1";
  const env = { ...process.env, ...devBackendEnv(role) };
  console.log(`[${role}] API http://${host}:${r.api} · web http://localhost:${r.web} · DB data/processed/${r.db}`);
  const { result } = concurrently(
    [
      { name: `${role}-api`, command: `node scripts/backend-dev.mjs --host ${host} --port ${r.api}`, env, prefixColor: "cyan.bold" },
      {
        name: `${role}-web`,
        command: `npm --prefix frontend run dev -- --port ${r.web} --strictPort`,
        env: { ...process.env, VITE_API_BASE_URL: `http://127.0.0.1:${r.api}` },
        prefixColor: "magenta.bold",
      },
    ],
    { cwd: ROOT, killOthers: ["failure", "success"], prefix: "name" },
  );
  result.then(
    () => process.exit(0),
    () => process.exit(1),
  );
}

function reset(roleArg) {
  requireVenv();
  const explicit = roleArg !== undefined;
  const role = parseRole(roleArg, process.env.STATION_ROLE ?? readBackendEnv("STATION_ROLE") ?? "ship");
  const env = { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1", STATION_ROLE: role };
  if (explicit) Object.assign(env, devBackendEnv(role));
  const child = spawn(VENV_PYTHON, ["-m", "app.cli", "reset"], { cwd: BACKEND, stdio: "inherit", env });
  child.on("exit", (code) => process.exit(code ?? 1));
}

function lanAddresses() {
  return Object.values(networkInterfaces())
    .flat()
    .filter((a) => a && a.family === "IPv4" && !a.internal)
    .map((a) => a.address);
}

function serve(roleArg, { port, build }) {
  requireVenv();
  const role = parseRole(roleArg, process.env.STATION_ROLE ?? readBackendEnv("STATION_ROLE") ?? "ship");
  // Varsayılan portta eski dev oturumunun izleyicisi de çakışır (uvicorn'u yeniden başlatır)
  if (port === ROLES[role].api) ensureClear([port], [role], role);
  else ensureClear([port], [], `--port ${port}`);
  if (build) {
    console.log("▶ Arayüz derleniyor (frontend/dist, aynı adres)…");
    const r = spawnSync("npm", ["--prefix", "frontend", "run", "build"], {
      cwd: ROOT,
      stdio: "inherit",
      shell: process.platform === "win32",
      env: { ...process.env, VITE_API_BASE_URL: "" },
    });
    if (r.status !== 0) process.exit(r.status ?? 1);
  }
  const home = role === "ship" ? "/me" : "/monitor";
  console.log(`\n▶ ${role === "ship" ? "Gemi" : "Dünya üssü"} istasyonu: http://0.0.0.0:${port}${home}`);
  for (const ip of lanAddresses()) console.log(`  ağdan: http://${ip}:${port}${home}`);
  const env = { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1", STATION_ROLE: role };
  const child = spawn(VENV_PYTHON, ["-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", String(port)], {
    cwd: BACKEND,
    stdio: "inherit",
    env,
  });
  for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => child.kill(sig));
  child.on("exit", (code) => process.exit(code ?? 0));
}

const [cmd, ...args] = process.argv.slice(2);
const positional = args.filter((a, i) => !a.startsWith("--") && args[i - 1] !== "--port");
const flags = new Set(args.filter((a) => a.startsWith("--")));
const role = positional[0];
const portIdx = args.indexOf("--port");
const port = portIdx >= 0 ? Number(args[portIdx + 1]) : 8000;
const portGiven = portIdx >= 0 && Number.isInteger(port) && port > 0;

if (cmd === "dev") dev(parseRole(role), { lan: flags.has("--lan") });
else if (cmd === "reset") reset(role);
else if (cmd === "serve") serve(role, { port, build: !flags.has("--no-build") });
else if (cmd === "stop") await stop(role, { extraPort: portGiven ? port : undefined, force: flags.has("--force") });
else if (cmd === "check") {
  const checked = parseRole(role, "ship");
  ensureClear([ROLES[checked].api, ROLES[checked].web], [checked], checked);
} else {
  console.error(
    "Kullanım: node scripts/station.mjs dev <ship|earth> [--lan] | reset [ship|earth] | serve [ship|earth] [--port N] [--no-build]" +
      " | stop [ship|earth] [--port N] [--force] | check [ship|earth]",
  );
  process.exit(2);
}
