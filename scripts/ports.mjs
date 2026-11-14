/**
 * Port ve süreç yardımcıları (ortak): bir portu hangi süreç dinliyor, o süreç kim, süreç ağacını kapat.
 *
 * Kullananlar: scripts/station.mjs (`npm run stop`, dev/serve öncesi kontrol) ve smoke testleri
 * (frontend/scripts/smoke-earth.ts). Neden gerekli: bug_read.md — Windows'ta bir geliştirme sunucusu zorla
 * durdurulunca süreç zinciri (npm → station.mjs → backend-dev.mjs → uvicorn, Vite) yaşamaya devam eder.
 *
 * Bağımlılığı yoktur; sadece işletim sisteminin araçlarını kullanır (Windows: netstat, taskkill, PowerShell;
 * diğerleri: lsof, ps).
 */
import { spawnSync } from "node:child_process";

export const isWin = process.platform === "win32";

/**
 * Bir TCP portunu dinleyen bütün süreçlerin PID'leri (tekrarsız; dinleyen yoksa boş dizi).
 * Windows'ta IPv4 ve IPv6 dinleyicilerinin ikisi de sayılır (0.0.0.0:5173 ve [::]:5173).
 * @param {number} port
 * @returns {number[]}
 */
export function listeningPids(port) {
  const pids = new Set();
  if (isWin) {
    const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8" });
    for (const line of (r.stdout ?? "").split(/\r?\n/)) {
      const p = line.trim().split(/\s+/);
      // TCP  0.0.0.0:8000  0.0.0.0:0  LISTENING  1234
      if (p.length >= 5 && p[0] === "TCP" && p[1].endsWith(`:${port}`) && p[3] === "LISTENING") pids.add(Number(p[4]));
    }
  } else {
    const r = spawnSync("lsof", ["-ti", `tcp:${port}`, "-sTCP:LISTEN"], { encoding: "utf-8" });
    for (const s of (r.stdout ?? "").trim().split(/\s+/)) if (s) pids.add(Number(s));
  }
  return [...pids].filter((pid) => Number.isFinite(pid) && pid > 0);
}

/**
 * Bir TCP portunu dinleyen sürecin PID'i (yoksa null).
 * @param {number} port
 * @returns {number | null}
 */
export function listeningPid(port) {
  return listeningPids(port)[0] ?? null;
}

/**
 * Süreci ve (Windows'ta) BÜTÜN alt süreçlerini kapatır. Windows: `taskkill /PID <pid> /T /F`; diğerleri: SIGTERM.
 * Süreç zaten yoksa sessizce geçer.
 * @param {number} pid
 */
export function killPid(pid) {
  if (isWin) {
    spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
    return;
  }
  try {
    process.kill(pid, "SIGTERM");
  } catch {
    /* süreç artık yok */
  }
}

/**
 * @typedef {object} ProcInfo
 * @property {number} pid
 * @property {number} ppid      üst sürecin PID'i (üst süreç ölmüş olabilir; PID başka bir sürece verilmiş olabilir)
 * @property {string} name      örn. node.exe, python.exe
 * @property {string} command   komut satırı (okunamadıysa "")
 * @property {number} started   başlangıç zamanı (ms, epoch); bilinmiyorsa 0
 */

/**
 * Çalışan bütün süreçler (tek sorguda). Bilgi okunamazsa boş dizi döner.
 * @returns {ProcInfo[]}
 */
export function listProcesses() {
  if (isWin) {
    const script =
      "[Console]::OutputEncoding = [Text.Encoding]::UTF8; " +
      "Get-CimInstance Win32_Process | ForEach-Object { " +
      "$t = if ($_.CreationDate) { [DateTimeOffset]::new($_.CreationDate.ToUniversalTime()).ToUnixTimeMilliseconds() } else { 0 }; " +
      "\"$($_.ProcessId)`t$($_.ParentProcessId)`t$t`t$($_.Name)`t$($_.CommandLine)\" }";
    const r = spawnSync("powershell", ["-NoProfile", "-NonInteractive", "-Command", script], {
      encoding: "utf-8",
      timeout: 30_000,
      maxBuffer: 64 * 1024 * 1024,
    });
    const out = [];
    for (const line of (r.stdout ?? "").split(/\r?\n/)) {
      const [pid, ppid, started, name, ...rest] = line.split("\t");
      if (!pid || !name) continue;
      out.push({ pid: Number(pid), ppid: Number(ppid), started: Number(started) || 0, name, command: rest.join("\t").trim() });
    }
    return out;
  }
  const r = spawnSync("ps", ["-axo", "pid=,ppid=,args="], { encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 });
  const out = [];
  for (const line of (r.stdout ?? "").split("\n")) {
    const m = /^\s*(\d+)\s+(\d+)\s+(.*)$/.exec(line);
    if (!m) continue;
    const command = m[3].trim();
    out.push({ pid: Number(m[1]), ppid: Number(m[2]), started: 0, name: (command.split(/\s+/)[0] ?? "").split("/").pop() ?? "", command });
  }
  return out;
}

/**
 * Tek bir sürecin adı ve komut satırı. Bilgi okunamazsa alanlar boş döner.
 * @param {number} pid
 * @returns {ProcInfo}
 */
export function describeProcess(pid) {
  return listProcesses().find((p) => p.pid === pid) ?? { pid, ppid: 0, name: "", command: "", started: 0 };
}

/**
 * Bir sürecin bütün alt süreçleri (çocuklar, torunlar…). PID yeniden kullanımına karşı: alt süreç üst süreçten
 * önce başlamış olamaz.
 * @param {number} pid
 * @param {ProcInfo[]} procs
 * @returns {ProcInfo[]}
 */
export function descendantsOf(pid, procs) {
  const byParent = new Map();
  for (const p of procs) {
    if (!byParent.has(p.ppid)) byParent.set(p.ppid, []);
    byParent.get(p.ppid).push(p);
  }
  const root = procs.find((p) => p.pid === pid);
  const out = [];
  const seen = new Set([pid]);
  const queue = [{ pid, started: root?.started ?? 0 }];
  while (queue.length) {
    const cur = queue.shift();
    for (const child of byParent.get(cur.pid) ?? []) {
      if (seen.has(child.pid)) continue;
      if (cur.started && child.started && child.started + 2000 < cur.started) continue; // PID yeniden kullanılmış
      seen.add(child.pid);
      out.push(child);
      queue.push(child);
    }
  }
  return out;
}

/**
 * Süreç ağacını kapatır: verilen süreç + bütün alt süreçleri. Windows: `taskkill /PID <pid> /T /F`;
 * diğerleri: önce alt süreçlere, sonra sürecin kendisine SIGTERM.
 * @param {number} pid
 * @param {ProcInfo[]} [procs] `listProcesses()` çıktısı (POSIX'te alt süreçleri bulmak için)
 */
export function killTree(pid, procs = []) {
  if (isWin) {
    spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
    return;
  }
  for (const p of [...descendantsOf(pid, procs).reverse(), { pid }]) {
    try {
      process.kill(p.pid, "SIGTERM");
    } catch {
      /* süreç artık yok */
    }
  }
}
