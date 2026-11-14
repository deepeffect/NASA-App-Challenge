#!/usr/bin/env node
/**
 * backend/.venv içindeki Python'u platformdan bağımsız çalıştırır (cwd = backend/).
 *   node scripts/py.mjs -m pytest
 *   node scripts/py.mjs -m app.cli seed --seed 42
 * Windows: backend\.venv\Scripts\python.exe · Linux/macOS: backend/.venv/bin/python
 */
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
export const BACKEND = join(ROOT, "backend");
export const VENV_PYTHON =
  process.platform === "win32"
    ? join(BACKEND, ".venv", "Scripts", "python.exe")
    : join(BACKEND, ".venv", "bin", "python");

function main() {
  if (!existsSync(VENV_PYTHON)) {
    console.error(`[py] ${VENV_PYTHON} bulunamadı. Önce kök klasörde: npm run setup`);
    process.exit(1);
  }
  const child = spawn(VENV_PYTHON, process.argv.slice(2), {
    cwd: BACKEND,
    stdio: "inherit",
    env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" },
  });
  for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => child.kill(sig));
  child.on("exit", (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) main();
