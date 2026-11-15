#!/usr/bin/env node
/**
 * Golden test düzeneği: referans prototipin JavaScript'ini (değiştirmeden) Node `vm` içinde, küçük bir
 * sahte DOM ile çalıştırır ve render() / renderCheckin() / ciSend() çıktılarını yapılandırılmış JSON
 * olarak verir. Python testleri (tests/golden/test_golden.py) aynı durumları Python koduyla üretip
 * karşılaştırır.
 *
 *   node prototype_harness.mjs <personal-artifact.html>  < spec.json  > out.json
 *
 * spec: {
 *   views:    [{ai, di, role: "astro"|"earth", share: null|"private"|"scores"|"full"}],
 *   strips:   [{ai, role}],
 *   checkins: [{ai, di, answers: [..], share: null|"private"|"scores"|"full"}]
 * }
 */
import { readFileSync } from "node:fs";
import vm from "node:vm";

const html = readFileSync(process.argv[2], "utf-8");
const dataMatch = html.match(/<script type="application\/json" id="data">([\s\S]*?)<\/script>/);
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
if (!dataMatch || scripts.length !== 1) throw new Error("Prototip beklenen yapıda değil");

// ------------------------------------------------------------------ sahte DOM
function makeEl(id) {
  const el = {
    id, innerHTML: "", textContent: "", value: "", hidden: false, open: false, disabled: false,
    placeholder: "", className: "", style: {}, dataset: {}, attrs: {}, clientWidth: 0, offsetWidth: 0, offsetLeft: 0,
    setAttribute(k, v) { this.attrs[k] = String(v); },
    removeAttribute(k) { delete this.attrs[k]; },
    getAttribute(k) { return this.attrs[k]; },
    addEventListener() {}, querySelectorAll() { return []; }, querySelector() { return null; },
    insertAdjacentHTML() {}, showModal() {}, close() {},
  };
  if (id === "strip") {
    el.children = Array.from({ length: 30 }, (_, k) => {
      const b = makeEl(`bar${k}`);
      b.firstChild = { style: {} };
      return b;
    });
  }
  return el;
}
const els = new Map();
const document = {
  getElementById(id) {
    if (!els.has(id)) {
      const el = makeEl(id);
      if (id === "data") el.textContent = dataMatch[1];
      els.set(id, el);
    }
    return els.get(id);
  },
};
const storage = () => { const m = new Map(); return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) }; };
const ctx = vm.createContext({
  document, window: { addEventListener() {} }, localStorage: storage(), sessionStorage: storage(),
  setTimeout, clearTimeout, console,
});
vm.runInContext(scripts[0], ctx, { filename: "personal-artifact.html" });
const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------------ HTML → yapı
const unesc = (s) => s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&amp;/g, "&");
const strip = (s) => unesc(s.replace(/<[^>]*>/g, "")).trim();

function parseTodo(h) {
  const title = h.match(/<h2>([\s\S]*?)<\/h2>/)[1];
  const calm = h.match(/<p class="calm">([\s\S]*?)<\/p>/);
  const ground = h.match(/<p class="ground"><b>([\s\S]*?)<\/b> ([\s\S]*?)<\/p>/);
  const items = [...h.matchAll(/<details class="item"><summary><b>([\s\S]*?)<\/b><span class="muted">([\s\S]*?)<\/span><\/summary>\s*<ol>([\s\S]*?)<\/ol>\s*<p class="muted">Contact ground if: ([\s\S]*?)<\/p><\/details>/g)].map(
    (m) => ({ title: unesc(m[1]), why: unesc(m[2]), steps: [...m[3].matchAll(/<li>([\s\S]*?)<\/li>/g)].map((x) => unesc(x[1])), contact: unesc(m[4]) }),
  );
  const masked = h.match(/<p class="muted" style="margin-top:8px">([\s\S]*?)<\/p>/);
  return {
    title: unesc(title), calm: calm ? unesc(calm[1]) : null,
    ground: ground ? { title: unesc(ground[1]), text: unesc(ground[2]) } : null,
    items, masked: masked ? unesc(masked[1]) : null,
  };
}

function parseTable(h) {
  const areas = [], readings = [];
  let group = null;
  for (const m of h.matchAll(/<tr( class="grp")?>([\s\S]*?)<\/tr>/g)) {
    const cells = [...m[2].matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map((x) => x[1]);
    if (!cells.length) continue; // başlık satırı (th)
    if (m[1]) { group = strip(cells[0]); continue; }
    if (group === "Area scores (0 to 100)") areas.push([strip(cells[0]), strip(cells[1]), strip(cells[3])]);
    else {
      const nm = cells[0].match(/^([\s\S]*?) <span class="unit">([\s\S]*?)<\/span>$/);
      readings.push([group, unesc(nm[1]), unesc(nm[2]), strip(cells[1]), strip(cells[2]), strip(cells[3])]);
    }
  }
  return { areas, readings };
}

const fakeCheckin = (share) => ({ step: 0, options: [], msgs: [{ who: "bot", text: "x" }], notes: [], done: true, share });

function view({ ai: a, di: d, role: r, share }) {
  vm.runInContext(`role = ${JSON.stringify(r)}; ai = ${a}; di = ${d};`, ctx);
  const key = vm.runInContext("A[ai].id + ':' + di", ctx);
  const checkins = vm.runInContext("checkins", ctx);
  if (share) checkins[key] = fakeCheckin(share);
  vm.runInContext("render()", ctx);
  const state = $("state").innerHTML;
  const glyph = state.match(/glyph g(\d)/);
  const out = {
    ai: a, di: d, role: r, share: share ?? null,
    state: strip(state), glyph: glyph ? Number(glyph[1]) : 0,
    statesub: $("statesub").textContent, score: $("score").textContent, daylabel: $("daylabel").textContent,
    todo: parseTodo($("todo").innerHTML), ...parseTable($("readings").innerHTML),
    privnote: $("privnote").textContent,
    ciearth: r === "earth" ? $("ciearth").innerHTML : null,
  };
  delete checkins[key];
  return out;
}

function stripOf({ ai: a, role: r }) {
  vm.runInContext(`role = ${JSON.stringify(r)}; ai = ${a}; di = A[ai].days.length - 1; render();`, ctx);
  return { ai: a, role: r, bars: $("strip").children.map((b) => [b.className, b.attrs["aria-label"]]) };
}

async function checkin({ ai: a, di: d, answers, share }) {
  vm.runInContext(`role = "astro"; ai = ${a}; di = ${d};`, ctx);
  const key = vm.runInContext("A[ai].id + ':' + di", ctx);
  const checkins = vm.runInContext("checkins", ctx);
  delete checkins[key];
  const send = vm.runInContext("ciSend", ctx);
  for (const ans of answers) await send(ans);
  const st = JSON.parse(JSON.stringify(checkins[key]));
  let earth = null;
  if (share) {
    checkins[key].share = share;
    vm.runInContext(`role = "earth"; render();`, ctx);
    earth = $("ciearth").innerHTML;
  }
  delete checkins[key];
  return { ai: a, di: d, answers, share: share ?? null, state: st, earth };
}

const spec = JSON.parse(readFileSync(0, "utf-8"));
const result = { views: (spec.views ?? []).map(view), strips: (spec.strips ?? []).map(stripOf), checkins: [] };
for (const c of spec.checkins ?? []) result.checkins.push(await checkin(c));
process.stdout.write(JSON.stringify(result));
