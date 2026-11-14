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
 * Seçenekler: --lan → API'yi 0.0.0.0'da dinlet (ağdaki diğer makineler bağlanabilsin).
 * Geliştirmede iki rol aynı EARTH_LINK_TOKEN'ı kullanır (ortamda yoksa "dev-link-token").
 */
import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import concurrently from "concurrently";

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

function requireVenv() {
  if (!existsSync(VENV_PYTHON)) {
    console.error(`${VENV_PYTHON} bulunamadı. Önce kök klasörde: npm run setup`);
    process.exit(1);
  }
}

function dev(role, { lan }) {
  requireVenv();
  const r = ROLES[role];
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

const [cmd, roleArg, ...rest] = process.argv.slice(2);
const flags = new Set(rest.concat(roleArg?.startsWith("--") ? [roleArg] : []));
const role = roleArg?.startsWith("--") ? undefined : roleArg;

if (cmd === "dev") dev(parseRole(role), { lan: flags.has("--lan") });
else if (cmd === "reset") reset(role);
else {
  console.error("Kullanım: node scripts/station.mjs dev <ship|earth> [--lan] | reset [ship|earth]");
  process.exit(2);
}
