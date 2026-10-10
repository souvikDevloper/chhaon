import { STR } from "./i18n.js";
import { classify as classifyLocal, guidance as guidanceLocal } from "./protocol.js";
import { listen } from "./listen.js";

// ---------------- state & storage ----------------
const store = {
  get(k, d = null) { try { const v = localStorage.getItem("chhaon." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("chhaon." + k, JSON.stringify(v)); } catch {} },
  del(k) { try { localStorage.removeItem("chhaon." + k); } catch {} },
};
const S = {
  lang: store.get("lang", "hi"),
  siteId: store.get("site"),
  day: "today",
  payload: null,
  feed: [],
  lastFeedTs: null,
  speaker: false,
  qa: [],
  selected: new Set(),
  incident: null,
  timers: [],
  wakeLock: null,
  audioUnlocked: false,
  offline: false,
  feedTimer: null,
  tickTimer: null,
  dayAudio: null, // today's announcements with their audio, cached for offline playback
  played: new Set(),
  listening: null, // an open Transcribe stream
  expectTest: false,
  incidentTimer: null,
  attention: null, // an open case is waiting for the supervisor's answer
};
const t = () => STR[S.lang];
const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------------- time (always India time, whatever the phone says) ----------------
function istNow() {
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).formatToParts(new Date()).map((p) => [p.type, p.value]));
  const h = +parts.hour, m = +parts.minute;
  return { h, m, hhmm: `${parts.hour}:${parts.minute}`, mins: h * 60 + m };
}
const toMins = (hhmm) => { const [h, m] = hhmm.split(":").map(Number); return h * 60 + m; };
const hhmmOf = (iso) => new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(iso));
const fmtTime = (iso) => say(hhmmOf(iso));

// how people say a time: "दोपहर 1 बजे", "शाम साढ़े 4 बजे"; "1 PM", "4:30 PM" (same rules as the spoken announcements)
function say(hhmm, lang = S.lang) {
  if (!hhmm) return "";
  let [h, m] = hhmm.split(":").map(Number);
  h %= 24;
  const h12 = h % 12 || 12;
  if (lang === "en") return m ? `${h12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}` : `${h12} ${h < 12 ? "AM" : "PM"}`;
  const period = h >= 4 && h < 12 ? "सुबह" : h >= 12 && h < 16 ? "दोपहर" : h >= 16 && h < 20 ? "शाम" : "रात";
  const clock = m === 0 ? `${h12} बजे` : m === 30 ? ({ 1: "डेढ़ बजे", 2: "ढाई बजे" }[h12] || `साढ़े ${h12} बजे`) : m === 15 ? `सवा ${h12} बजे` : m === 45 ? `पौने ${(h12 % 12) + 1} बजे` : `${h12}:${String(m).padStart(2, "0")} बजे`;
  return `${period} ${clock}`;
}
function span(a, b) {
  if (S.lang !== "hi") return `${say(a)}–${say(b)}`;
  const [pa, ...ca] = say(a).split(" "), [pb] = say(b).split(" ");
  // "सुबह 6 से सवा 7 बजे तक", not "सुबह 6 बजे से सुबह सवा 7 बजे तक"
  return pa === pb ? `${pa} ${ca.join(" ").replace(/ बजे$/, "")} से ${say(b).slice(pb.length + 1)} तक` : `${say(a)} से ${say(b)} तक`;
}

// ---------------- api ----------------
async function api(path, opts = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeout || 25000);
  try {
    const res = await fetch("/api" + path, {
      method: opts.method || (opts.body ? "POST" : "GET"),
      headers: opts.body ? { "content-type": "application/json" } : undefined,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
      signal: ctrl.signal,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw Object.assign(new Error(data.error || res.statusText), { status: res.status });
    S.offline = false;
    return data;
  } catch (e) {
    if (e.name === "AbortError" || e instanceof TypeError) S.offline = true;
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

function toast(msg, ms = 3200) {
  const el = document.createElement("div");
  el.className = "toast";
  el.setAttribute("role", "status");
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), ms);
}

// ---------------- audio ----------------
const player = new Audio();
player.preload = "auto";
function unlockAudio() {
  if (S.audioUnlocked) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const b = ctx.createBuffer(1, 1, 22050);
    const src = ctx.createBufferSource();
    src.buffer = b; src.connect(ctx.destination); src.start(0);
    S.audioUnlocked = true;
  } catch {}
}
// a two-tone chime so heads turn before the words start (works offline, no file)
function chime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [[880, 0], [660, 0.28]].forEach(([f, at]) => {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.value = f; o.connect(g); g.connect(ctx.destination);
      g.gain.setValueAtTime(0.0001, ctx.currentTime + at);
      g.gain.exponentialRampToValueAtTime(0.5, ctx.currentTime + at + 0.03);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + at + 0.26);
      o.start(ctx.currentTime + at); o.stop(ctx.currentTime + at + 0.3);
    });
    setTimeout(() => ctx.close(), 900);
  } catch {}
}
function play(url, key) {
  if (!url) return;
  const announcement = !!key; // site announcements: chime first, then say it twice over the noise
  const go = () => {
    player.src = url;
    let times = announcement ? 2 : 1;
    player.onended = () => { if (--times > 0) setTimeout(() => player.play().catch(() => {}), 1200); };
    player.play().then(() => {
      if (key && S.siteId) api(`/sites/${S.siteId}/played`, { body: { key } }).catch(() => {});
    }).catch(() => toast(t().listen + " ▶"));
  };
  if (announcement) { chime(); setTimeout(go, 800); } else go();
}
async function keepAwake() {
  try { if ("wakeLock" in navigator && !S.wakeLock) S.wakeLock = await navigator.wakeLock.request("screen"); } catch {}
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && S.speaker) { S.wakeLock = null; keepAwake(); if (S.wasHidden) toast(t().keepOpen, 6000); S.wasHidden = false; }
  if (document.visibilityState === "hidden" && S.speaker) S.wasHidden = true;
});

// ---------------- icons ----------------
const I = {
  logo: `<svg viewBox="0 0 40 40" aria-hidden="true"><circle cx="27" cy="12" r="7" fill="#c8510c"/><path d="M4 22c4-9 26-9 32 0z" fill="#0e5e57"/><rect x="19" y="21" width="2.4" height="15" rx="1.2" fill="#0e5e57"/><path d="M8 36h24" stroke="#13221f" stroke-width="2.4" stroke-linecap="round"/></svg>`,
  today: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>`,
  unwell: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/><rect x="2.5" y="2.5" width="19" height="19" rx="5"/></svg>`,
  ask: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 5h16v11H9l-5 4z"/><path d="M8 9.5h8M8 12.5h5"/></svg>`,
  replay: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><path d="M12 8v4l3 2"/></svg>`,
  play: `<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4v16l13-8z"/></svg>`,
  gear: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" width="18" height="18"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>`,
};
const SYM_EMOJI = { confused: "🌀", unconscious: "🛌", seizure: "⚡", hot_dry_skin: "🔥", cannot_drink: "🚱", dizzy: "😵‍💫", headache: "🤕", vomiting: "🤮", nausea: "🤢", weak: "😩", heavy_sweating: "💦", fainted_recovered: "😵", cramps: "🦵", rash: "🔴" };
const RED = ["confused", "unconscious", "seizure", "hot_dry_skin", "cannot_drink"];
const OTHER = ["dizzy", "headache", "vomiting", "nausea", "weak", "heavy_sweating", "fainted_recovered", "cramps", "rash"];

// ---------------- shell ----------------
function shell() {
  const route = location.hash.slice(2).split("/")[0] || "";
  const tab = (id, href, icon, label, cls = "") =>
    `<a href="#/${href}" class="${cls}" ${route === href || (href === "unwell" && route === "incident") || (href === "replay" && route === "replay") ? 'aria-current="page"' : ""}>${icon}<span>${label}</span></a>`;
  return `
  <div class="frame">
    <div class="app">
      <header class="top">
        <a class="brand" href="#/today" aria-label="Chhaon">${I.logo}<span><b>${t().appName}</b><small>${S.lang === "hi" ? "Chhaon" : "छाँव · shade"}</small></span></a>
        <span class="spacer"></span>
        ${S.siteId ? `<a class="chip-btn" href="#/site" aria-label="${esc(t().siteTitle)}" style="display:inline-flex;align-items:center;gap:6px;text-decoration:none">${I.gear}</a>` : ""}
        <button class="chip-btn" data-action="lang" lang="${S.lang === "hi" ? "en" : "hi"}">${t().lang}</button>
      </header>
      ${S.offline ? `<div class="banner" role="status">${t().offline}</div>` : ""}
      ${S.attention ? `<a class="attention" href="#/incident/${esc(S.attention.split("|")[0])}" role="alert">${t().recheckBanner}</a>` : ""}
      ${S.speaker && S.siteId ? `<a class="speakerbar" href="#/today" role="status">${esc(t().speakerBar(nextAnnouncement()))}</a>` : ""}
      <main id="main" tabindex="-1"></main>
      ${S.siteId ? `<nav class="tabs" aria-label="Main">
        ${tab("today", "today", I.today, t().tabToday)}
        ${tab("unwell", "unwell", I.unwell, t().tabUnwell, "urgent")}
        ${tab("ask", "ask", I.ask, t().tabAsk)}
      </nav>` : ""}
    </div>
    <aside class="tour" aria-label="Guided tour">${tourHtml()}</aside>
  </div>`;
}

function tourHtml() {
  const en = S.lang === "en";
  return `
    <h2>${en ? "Try Chhaon in five steps" : "पाँच कदम में छाँव देखिए"}</h2>
    <p>${en ? "Built for a site supervisor in the sun. Each step runs on AWS for real." : "धूप में खड़े सुपरवाइज़र के लिए बना। हर कदम असल में AWS पर चलता है।"}</p>
    <ol>
      <li><div><b>${en ? "See today's plan" : "आज का प्लान देखिए"}</b><span>${en ? "Hour-by-hour WBGT for the site, and how the shift moves out of the unsafe hours." : "साइट का हर घंटे का WBGT, और शिफ़्ट ख़तरनाक घंटों से कैसे हटती है।"}</span> <a href="#/today">${en ? "Open" : "खोलिए"}</a></div></li>
      <li><div><b>${en ? "Hear a break, on time" : "ब्रेक की घोषणा सुनिए"}</b><span>${en ? "Turn on announcements, then 'Test announcement in 1 minute'. EventBridge Scheduler fires, Polly speaks Hindi." : "घोषणाएँ चालू करें, फिर '1 मिनट में जाँच'। EventBridge Scheduler चलता है, Polly हिंदी बोलता है।"}</span></div></li>
      <li><div><b>${en ? "Report a dizzy worker" : "चक्कर वाले साथी की सूचना"}</b><span>${en ? "Pick 'Dizzy' and 'Vomiting'. A Step Functions protocol re-checks in 20 s; answer 'Getting worse' to see the emergency path with nearby hospitals." : "'चक्कर' और 'उल्टी' चुनिए। Step Functions 20 सेकंड में दोबारा पूछेगा; 'बिगड़ रहा है' दबाइए।"}</span> <a href="#/unwell">${en ? "Open" : "खोलिए"}</a></div></li>
      <li><div><b>${en ? "Ask in Hindi" : "हिंदी में पूछिए"}</b><span>${en ? "'कल दोपहर 2 बजे ढलाई कर सकते हैं?' A Strands agent on Bedrock runs the planner as a tool and shows its working." : "'कल दोपहर 2 बजे ढलाई कर सकते हैं?' Bedrock पर Strands एजेंट प्लानर से हिसाब करके बताता है।"}</span> <a href="#/ask">${en ? "Open" : "खोलिए"}</a></div></li>
      <li><div><b>${en ? "Replay 30 May 2024" : "30 मई 2024 दोहराइए"}</b><span>${en ? "Rourkela, the day ten heatstroke deaths were reported. What Chhaon would have said with that day's weather." : "राउरकेला, जिस दिन लू से दस मौतें दर्ज हुईं। उस दिन के मौसम पर छाँव क्या कहता।"}</span> <a href="#/replay/rourkela-2024-05-30">${en ? "Open" : "खोलिए"}</a></div></li>
    </ol>
    <dl class="aws">
      <dt>Lambda</dt><dd>${en ? "WBGT (Liljegren) and the shift planner, deterministic and unit-tested" : "WBGT (Liljegren) और शिफ़्ट प्लानर"}</dd>
      <dt>EventBridge Scheduler</dt><dd>${en ? "one timer per break, deleted after it fires" : "हर ब्रेक का अपना टाइमर"}</dd>
      <dt>Step Functions</dt><dd>${en ? "heat-illness protocol: waits, re-checks, escalation" : "बीमारी प्रोटोकॉल: इंतज़ार, दोबारा जाँच, आगे सूचना"}</dd>
      <dt>Polly · Location</dt><dd>${en ? "Hindi voice for breaks and crew voice notes; nearest hospitals" : "ब्रेक और मज़दूरों के लिए हिंदी आवाज़; नज़दीकी अस्पताल"}</dd>
      <dt>Transcribe · Bedrock · Strands Agents</dt><dd>${en ? "ask by voice in Hindi; the assistant uses the planner as its tools" : "हिंदी में बोलकर पूछिए; सहायक प्लानर को टूल की तरह चलाता है"}</dd>
      <dt>DynamoDB · CloudFront · CloudWatch</dt><dd>${en ? "state, delivery, and an impact dashboard" : "डेटा, डिलीवरी, असर का डैशबोर्ड"}</dd>
    </dl>`;
}

// ---------------- views ----------------
function viewWelcome() {
  return `<section class="welcome">
    <div class="sun-ribbon" aria-hidden="true"></div>
    <h1>${S.lang === "hi" ? "छाँव" : "Chhaon"}</h1>
    <p class="sub">${t().tagline}</p>
    <p>${t().welcomeLead}</p>
    <div class="row">
      <button class="btn block" data-action="demo">${t().tryDemo}</button>
      <a class="btn ghost block" href="#/site">${t().setupMine}</a>
    </div>
    <p class="small" style="margin-top:22px">${S.lang === "hi" ? "विधि: Liljegren WBGT मॉडल, ACGIH सीमाएँ, NCDC (स्वास्थ्य मंत्रालय) की प्राथमिक उपचार गाइड।" : "Method: Liljegren WBGT model, ACGIH screening limits, NCDC (Health Ministry) first-aid guidance."} <a href="#/about">${t().about}</a></p>
  </section>`;
}

function nowState(p) {
  const n = istNow();
  const hours = p.crew.hours;
  const cur = hours.find((x) => x.hour === n.h);
  const work = hours.filter((x) => x.work_minutes > 0);
  const nextEv = (p.events || []).find((e) => e.at > n.hhmm);
  let status, sub = "", band = cur && cur.status !== "off" ? (cur.status === "stop" ? "stop" : cur.band) : "shade";
  const workName = t().workload[p.workload] || t().workload.heavy;
  if (!work.length) { status = t().nowNoWork; band = "stop"; }
  else if (n.hhmm < work[0].start) { status = t().nowBefore(say(p.crew.first_start)); band = "shade"; }
  else if (n.mins >= toMins(p.crew.last_end)) { status = t().nowAfter; band = "shade"; }
  else if (cur && cur.status === "work") {
    if (n.m < cur.work_minutes) { status = t().nowWork(cur.work_minutes, cur.rest_minutes); sub = t().nowWorkLeft(cur.work_minutes - n.m); }
    else { status = t().nowRest(say(`${String(n.h + 1).padStart(2, "0")}:00`)); }
  } else if (cur && cur.status === "stop") {
    const until = (p.crew.stop_windows.find(([a, b]) => a <= n.hhmm && n.hhmm < b) || [null, nextEv?.at || ""])[1];
    status = t().nowStop(say(until), workName);
  } else { status = t().nowFree; }
  return { cur, status, sub, band, nextEv, n };
}

function stripHtml(hours, mode, nowH) {
  const cols = hours.filter((h) => h.status !== "off" || h.in_normal_shift);
  const style = `grid-template-columns: repeat(${cols.length}, minmax(0,1fr))`;
  if (mode === "normal") {
    return `<div class="strip normal" style="${style}" aria-label="${esc(t().normalRow)}">${cols.map((h) => `<div class="h"><div class="bar ${h.in_normal_shift ? "worked" : ""} ${h.normal_overexposure > 0 ? "over" : ""}" title="${h.start}"></div></div>`).join("")}</div>`;
  }
  return `<div class="strip" style="${style}" aria-label="${esc(t().chhaonRow)}">${cols.map((h) => {
    const cls = h.status === "stop" ? "b-stop" : `b-${h.band}`;
    const pct = Math.round((h.work_minutes / 60) * 100);
    const label = `${h.start} WBGT ${h.wbgt}°C, ${h.work_minutes} ${t().minutes}`;
    return `<div class="h"><span class="w">${Math.round(h.wbgt)}</span><div class="bar ${cls} ${h.hour === nowH ? "now-col" : ""}" title="${esc(label)}" aria-label="${esc(label)}"><div class="fill" style="height:${h.status === "stop" ? 0 : pct}%"></div></div><span class="t">${h.hour % 12 || 12}</span></div>`;
  }).join("")}</div>${periodsHtml(cols)}`;
}

function periodsHtml(cols) {
  // "सुबह | दोपहर | शाम" under the 12-hour numbers, so 1 and 6 can't be confused
  const name = (h) => (h < 12 ? "morning" : h < 16 ? "noon" : "evening");
  const groups = [];
  for (const c of cols) {
    const k = name(c.hour);
    if (groups.length && groups[groups.length - 1].k === k) groups[groups.length - 1].n++;
    else groups.push({ k, n: 1 });
  }
  return `<div class="periods" style="grid-template-columns:${groups.map((g) => `${g.n}fr`).join(" ")}" aria-hidden="true">${groups.map((g) => `<span>${t().periods[g.k]}</span>`).join("")}</div>`;
}

function fmtDate(iso) {
  return new Intl.DateTimeFormat(S.lang === "hi" ? "hi-IN" : "en-IN", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(iso + "T00:00:00Z"));
}

function fmtMins(m) {
  const h = Math.floor(m / 60), r = m % 60;
  if (S.lang === "hi") return h ? `${h} घंटे${r ? ` ${r} मिनट` : ""}` : `${r} मिनट`;
  return h ? `${h} h${r ? ` ${r} min` : ""}` : `${r} min`;
}

function viewToday() {
  const P = S.payload;
  if (!P) return `<div class="skeleton" aria-label="${t().loading}"></div>`;
  const p = P.plan, site = P.site, isToday = S.day === "today";
  const ns = nowState(p);
  const nowCard = isToday ? `
    <section class="now ${ns.band}" aria-live="polite">
      <p class="status">${esc(ns.status)}</p>
      ${ns.sub ? `<p class="sub">${esc(ns.sub)}</p>` : ""}
      <div class="wbgt"><b>${ns.cur ? ns.cur.wbgt.toFixed(1) : "–"}°</b><span>${t().wbgtLabel}<br>${ns.cur ? `${ns.cur.air_temp}°C, ${ns.cur.humidity}%` : ""}</span><button data-action="wbgt-help" aria-label="WBGT?">?</button></div>
    </section>
    <div id="wbgt-help" class="help" hidden>${t().wbgtHelp}</div>
    ${ns.nextEv ? `<p class="next">${t().next(say(ns.nextEv.at), t().kinds[ns.nextEv.kind], toMins(ns.nextEv.at) - ns.n.mins)}</p>` : ""}` : `
    <section class="now ${p.verdict === "normal" ? "safe" : p.verdict === "adjusted" ? "caution" : "stop"}">
      <p class="status">${p.crew.first_start ? t().nowBefore(say(p.crew.first_start)) : t().nowNoWork}</p>
      <p class="sub">${p.crew.stop_windows.map(([a, b]) => `${esc(t().workload[p.workload])}: ${span(a, b)} ${S.lang === "hi" ? "बंद" : "stopped"}`).join(" · ") || t().impactNormal}</p>
      <div class="wbgt"><b>${p.peak_wbgt?.toFixed(1) ?? "–"}°</b><span>${t().wbgtLabel}<br>${S.lang === "hi" ? "सबसे ज़्यादा" : "peak"} ${say(p.peak_time)}</span></div>
    </section>`;

  const newbie = p.new_workers && site.new_workers > 0 ? (() => {
    if (p.new_workers.exposure_factor >= 1) return `<p class="note">${esc(t().newWorkersCool(site.new_workers))}</p>`;
    return `<p class="note">${esc(t().newWorkers(site.new_workers, site.new_worker_day || 1, fmtMins(p.new_workers.planned_minutes), workRanges(p.new_workers.hours) || "–"))}</p>`;
  })() : "";

  const impact = p.verdict === "normal" ? t().impactNormal : t().impact(p.unsafe_hours_avoided, fmtMins(p.crew.planned_minutes), fmtMins(p.crew.target_minutes), Math.round(p.worker_hours_protected), p.normal_minutes_per_hour || 45);
  const sh = P.shade, lt = P.lighter;
  const lighterCard = lt ? `<section class="card shade-card">
      <h3>${t().lighterTitle}</h3>
      <p>${esc(t().lighter(t().workload[lt.workload], lt.stop_windows.map(([a, b]) => span(a, b)).join(", "), fmtMins(lt.minutes), lt.worker_hours, lt.rupees.toLocaleString("en-IN")))}</p>
      <p class="small">${esc(t().workloadEg[lt.workload])}</p>
    </section>` : "";
  const shadeCard = sh ? `<section class="card shade-card">
      <h3>${t().shadeTitle}</h3>
      <p>${esc(t().shade(fmtMins(sh.gain_minutes), sh.gain_worker_hours, sh.gain_rupees.toLocaleString("en-IN"), sh.stop_windows.map(([a, b]) => span(a, b)).join(", ")))}</p>
      <p class="small">${t().shadeNote} ${esc(t().wageNote(P.day_wage || 600))}</p>
    </section>` : "";
  const feedItems = S.feed.slice(-6).reverse();
  return `
    <div class="site-head">
      <div><h2>${esc(site.name)}</h2><div class="meta">${site.crew} ${t().crew}${site.shaded ? `, ${t().roof}` : ""}</div></div>
      <div class="daypick" role="group" aria-label="Day">
        <button data-action="day" data-day="today" aria-pressed="${isToday}">${t().today}</button>
        <button data-action="day" data-day="tomorrow" aria-pressed="${!isToday}">${t().tomorrow}</button>
      </div>
    </div>
    <div class="workpick" role="group" aria-label="${esc(t().siteWork)}">${["light", "moderate", "heavy", "very_heavy"].map((k) => `<button data-action="set-work" data-v="${k}" aria-pressed="${site.workload === k}">${esc(t().workload[k])}</button>`).join("")}</div>
    ${nowCard}
    <section class="plan">
      <h3>${isToday ? t().planTitle : t().planTitleTomorrow}</h3>
      <div class="strip-label">${t().normalRow}</div>
      ${stripHtml(p.crew.hours, "normal")}
      <div class="strip-label">${t().chhaonRow}</div>
      ${stripHtml(p.crew.hours, "plan", isToday ? ns.n.h : -1)}
      <p class="legend">${t().legend}</p>
      <p class="impact">${esc(impact)}</p>
      ${p.water_litres_total ? `<p class="water">${esc(t().water(p.water_litres_total, p.water_litres_per_worker))}</p>` : ""}
      ${p.crew.shortfall_minutes > 0 ? `<p class="note">${esc(t().shortfall(fmtMins(p.crew.shortfall_minutes)))}</p>` : ""}
      ${newbie}
    </section>
    <section class="card crew-card">
      <button class="btn block" data-action="brief">${t().brief}</button>
      <p class="small" style="margin:8px 0 10px">${t().briefHelp}</p>
      <a class="btn ghost block" href="${esc(shareUrl(P))}" target="_blank" rel="noopener">${t().share}</a>
    </section>
    ${lighterCard}
    ${shadeCard}
    ${isToday ? `<section class="card">
      <h3>${t().speaker}</h3>
      <p>${S.speaker ? esc(t().speakerOn(p.events.filter((e) => e.at > ns.n.hhmm).length)) : t().speakerOff}</p>
      <div class="row">
        ${S.speaker ? "" : `<button class="btn" data-action="speaker-on">${t().speakerStart}</button>`}
        <button class="btn ghost" data-action="test-announce">${t().speakerTest}</button>
        ${ns.nextEv ? `<button class="btn ghost" data-action="preview" data-kind="${ns.nextEv.kind}" data-minutes="${ns.nextEv.minutes}" data-until="${ns.nextEv.until || ""}">${I.play} ${t().listen}</button>` : ""}
      </div>
      <ul class="feed">${feedItems.length ? feedItems.map(feedItem).join("") : `<li><span class="txt small">${t().feedEmpty}</span></li>`}</ul>
    </section>` : ""}
    <a class="replay-card" href="#/replay/aurangabad-2024-05-30">${t().replayCard}</a>`;
}

function workRanges(hours) {
  const hm = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
  const out = [];
  let start = null, last = null;
  const flush = () => { if (start) out.push(span(start, hm(last.hour * 60 + last.work_minutes))); start = null; };
  for (const h of hours) {
    if (h.work_minutes > 0) { if (!start) start = h.start; last = h; }
    else flush();
  }
  flush();
  return out.join(", ");
}

function shareUrl(P) {
  const p = P.plan;
  const text = t().shareText(P.site.name, fmtDate(P.date), workRanges(p.crew.hours) || "–", p.crew.stop_windows.map(([a, b]) => span(a, b)).join(", "), `${say(p.peak_time)} (WBGT ${p.peak_wbgt}°C)`, t().workload[p.workload]);
  return `https://wa.me/?text=${encodeURIComponent(text)}`;
}

function feedItem(f) {
  if (f.type === "announcement") {
    const audio = f.audio?.[S.lang] || Object.values(f.audio || {})[0];
    return `<li><span class="when">${fmtTime(f.ts)}</span><span class="txt">${esc(f.text?.[S.lang] || "")}</span>${audio ? `<button class="icon-btn" data-action="play" data-src="${esc(audio)}" aria-label="${t().listen}">${I.play}</button>` : ""}</li>`;
  }
  if (f.type === "incident" || f.type === "alert") {
    return `<li class="alert"><span class="when">${fmtTime(f.ts)}</span><a class="txt" href="#/incident/${esc(f.incident_id)}">${f.type === "alert" ? t().feedAlert : t().feedReport(f.worker || "")}</a></li>`;
  }
  return "";
}

function viewUnwell() {
  const tile = (k, red) => `<button class="sym ${red ? "red" : ""}" data-action="sym" data-sym="${k}" aria-pressed="${S.selected.has(k)}"><span class="e" aria-hidden="true">${SYM_EMOJI[k]}</span>${esc(t().symptoms[k])}</button>`;
  return `
    <a class="btn red block call-top" href="tel:108">${t().call108Top}</a>
    <h1 class="view-title">${t().unwellTitle}</h1>
    <p class="lead">${t().unwellLead}</p>
    <div class="sym-group red">${t().redFlags}</div>
    <div class="syms">${RED.map((k) => tile(k, true)).join("")}</div>
    <div class="sym-group">${t().otherSymptoms}</div>
    <div class="syms">${OTHER.map((k) => tile(k, false)).join("")}</div>
    <label class="field"><span>${t().workerName}</span><input id="worker" autocomplete="off" maxlength="40"></label>
    <button class="btn red block" data-action="start-incident">${t().startProtocol}</button>`;
}

function viewIncident() {
  const inc = S.incident;
  if (!inc) return `<div class="skeleton"></div>`;
  const g = inc.guidance;
  const lvl = inc.level === "resolved" ? "green" : inc.level;
  const q = inc.pending;
  const question = q ? `<section class="ask-card" aria-live="assertive">
      <p>${esc(inc.timeline.filter((x) => x.kind === "question").slice(-1)[0]?.text || "")}</p>
      <div class="answers">${q.options.map((o) => `<button class="btn ${o === "worse" ? "red" : o === "better" ? "" : "ghost"} block" data-action="answer" data-answer="${o}">${esc(t().answers[o])}</button>`).join("")}</div>
    </section>` : "";
  const emergency = lvl === "red";
  const open = !["resolved", "handed_over"].includes(inc.status);
  const steps = `<h3 style="margin-top:20px">${t().steps}</h3>
    <ol class="steps">${g.steps.map((s) => `<li><span>${esc(s)}</span></li>`).join("")}</ol>`;
  const site = inc.site || S.payload?.site;
  const where = emergency && open && site?.lat != null ? `<div class="tell108"><b>${t().tell108}</b> ${esc(site.name || "")} · ${(+site.lat).toFixed(5)}, ${(+site.lon).toFixed(5)}
      <a href="https://wa.me/?text=${encodeURIComponent(`${t().myLocation}: https://maps.google.com/?q=${site.lat},${site.lon}`)}" target="_blank" rel="noopener">${t().shareLocation}</a></div>` : "";
  const worse = open && !emergency && !(q && q.question === "recheck") && !inc.local ? `<button class="btn red block" data-action="escalate">${t().gettingWorse}</button>` : "";
  return `
    <section class="level ${lvl}">
      <h2>${esc(g.title)}</h2>
      <div>${esc(inc.worker)}: ${inc.symptoms.map((s) => esc(t().symptoms[s] || s)).join(", ")}</div>
      ${inc.status !== "emergency" ? `<div><b>${esc(t().status[inc.status] || inc.status)}</b></div>` : ""}
      ${g.call_108 || (open && lvl !== "green") ? `<a class="btn block" href="tel:108">📞 ${t().call108}</a>` : ""}
    </section>
    ${where}
    ${worse}
    ${emergency ? steps + question : question + steps}
    ${inc.hospitals?.length ? `<h3 style="margin-top:20px">${t().hospitals}</h3><ul class="hosp">${inc.hospitals.map((h) => `<li><b>${esc(h.name)}</b><span class="small">${esc(h.address || "")}${h.distance_m ? ` · ${(h.distance_m / 1000).toFixed(1)} km` : ""}</span><div class="row">${h.phone ? `<a href="tel:${esc(h.phone)}">📞 ${esc(h.phone)}</a>` : ""}<a href="https://www.google.com/maps/dir/?api=1&destination=${h.lat},${h.lon}" target="_blank" rel="noopener">${t().directions}</a></div></li>`).join("")}</ul>` : ""}
    <h3 style="margin-top:20px">${t().timeline}</h3>
    <ul class="timeline">${inc.timeline.map((x) => `<li><time>${fmtTime(x.t)}</time>${esc(x.kind === "answer" ? t().answers[x.text] || x.text : x.kind === "reported" ? x.text.split(", ").map((s) => t().symptoms[s] || s).join(", ") : x.text)}</li>`).join("")}</ul>
    ${inc.local ? `<p class="note">${t().offlineIncident}</p>` : ""}
    ${inc.demo ? `<p class="small" style="margin-top:12px">${t().demoNote}</p>` : ""}
    <p class="small">${esc(g.source)}</p>`;
}

function viewAsk() {
  return `
    <h1 class="view-title">${t().askTitle}</h1>
    <p class="lead">${t().askLead}</p>
    <div class="chips">${t().askChips.map((c) => `<button data-action="chip">${esc(c)}</button>`).join("")}</div>
    <form class="ask-form" data-action="ask">
      <label class="vh" for="q">${t().askTitle}</label>
      <input id="q" name="q" placeholder="${esc(t().askPlaceholder)}" autocomplete="off" maxlength="400">
      ${(navigator.mediaDevices?.getUserMedia || "webkitSpeechRecognition" in window) ? `<button type="button" class="icon-btn mic ${S.listening ? "on" : ""}" style="width:52px;height:52px" data-action="mic" aria-label="${t().askMic}">🎤</button>` : ""}
      <button class="btn" type="submit">${t().askSend}</button>
    </form>
    <div class="qa">${S.qa.map((x, i) => `
      <p class="q">${x.via === "transcribe" ? `<span class="via">🎤 Amazon Transcribe</span> ` : ""}${esc(x.q)}</p>
      <div class="a">${x.a ? esc(x.a.answer) : esc(t().askThinking)}</div>
      ${x.a?.protocol ? `<div class="protocol"><b>${t().askProtocol}: ${esc(x.a.protocol.title)}</b><ol class="steps">${x.a.protocol.steps.map((st) => `<li><span>${esc(st)}</span></li>`).join("")}</ol>${x.a.protocol.call_108 ? `<a class="btn red block" href="tel:108">📞 ${t().call108}</a>` : ""}</div>` : ""}
      ${x.a?.facts ? `<div class="facts">📋 ${esc(x.a.facts)}</div>` : ""}
      ${x.a?.trace?.length ? `<div class="trace">${t().askTrace}: ${x.a.trace.map((c) => `<code>${esc(c.tool)}(${esc(Object.entries(c.args || {}).map(([k, v]) => `${k}=${Array.isArray(v) ? v.join("+") : v}`).join(", "))})</code>`).join(" ")}</div>` : ""}
      ${x.a ? `<div class="ev">${x.a.model_unavailable ? esc(t().askFallback) : esc(t().askEvidence((x.a.tools_used || []).join(", ") || "plan"))}${x.a.engine && x.a.engine !== "rules" ? `${x.a.engine.startsWith("strands") ? " · Strands Agents" : ""} · Amazon Bedrock${x.a.model ? ` · ${esc(String(x.a.model).split(".").pop())}` : ""}` : ""}</div>
      <button class="btn ghost" style="margin-top:8px" data-action="speak" data-i="${i}">${I.play} ${t().speakAnswer}</button>` : ""}`).reverse().join("")}</div>`;
}

let replayList = null;
function viewReplayList() {
  return `
    <h1 class="view-title">${t().replayTitle}</h1>
    <p class="lead">${t().replayLead}</p>
    <div class="replay-list">${(replayList || []).map((r) => `<a href="#/replay/${esc(r.key)}"><b>${esc(r.place)}</b><span class="small">${esc(fmtDate(r.date))}</span></a>`).join("") || `<div class="skeleton"></div>`}</div>`;
}

let replayData = {};
function viewReplay(key) {
  const R = replayData[key];
  if (!R) return `<div class="skeleton"></div>`;
  const p = R.plan, m = R.replay;
  const stops = p.crew.stop_windows.map(([a, b]) => span(a, b)).join(", ") || "–";
  const cols = p.crew.hours.filter((h) => h.status !== "off" || h.in_normal_shift);
  const official = m.official_window ? `<div class="strip-label">${esc(t().replayOfficial(say(m.official_window[0]), say(m.official_window[1])))}</div>
    <div class="official" style="display:grid;grid-template-columns:repeat(${cols.length},minmax(0,1fr))">${cols.map((h) => `<span style="background:${h.start >= m.official_window[0] && h.start < m.official_window[1] ? "var(--ink)" : "transparent"}"></span>`).join("")}</div>` : "";
  return `
    <a href="#/replay" class="small">${t().replayTitle}</a>
    <h1 class="view-title">${esc(m.place)}<br>${esc(fmtDate(m.date))}</h1>
    <section class="now stop"><p class="status">${esc(t().replayVerdict(stops))}</p>
      <div class="wbgt"><b>${p.peak_wbgt?.toFixed(1)}°</b><span>${t().wbgtLabel}<br>${S.lang === "hi" ? "सबसे ज़्यादा" : "peak"} ${say(p.peak_time)}</span></div></section>
    <section class="plan">
      <div class="strip-label">${t().normalRow}</div>${stripHtml(p.crew.hours, "normal")}
      <div class="strip-label">${t().chhaonRow} (${esc(t().workload[p.workload])})</div>${stripHtml(p.crew.hours, "plan", -1)}
      ${official}
      <p class="legend">${t().legend}</p>
      <p class="impact">${esc(t().impact(p.unsafe_hours_avoided, fmtMins(p.crew.planned_minutes), fmtMins(p.crew.target_minutes), Math.round(p.worker_hours_protected), p.normal_minutes_per_hour || 45))}</p>
    </section>
    ${(() => {
      const day = p.crew.hours.filter((h) => h.hour >= 6 && h.hour < 19);
      const hot = day.reduce((a, b) => (b.air_temp > a.air_temp ? b : a));
      const bad = day.reduce((a, b) => (b.wbgt > a.wbgt ? b : a));
      const outside = m.official_window ? day.filter((h) => h.status === "stop" && !(h.start >= m.official_window[0] && h.start < m.official_window[1])).length : 0;
      return `<div class="card contrast"><p class="hot">${esc(t().hottestAir(say(hot.start), hot.air_temp))}</p><p class="bad">${esc(t().mostDangerous(say(bad.start), bad.wbgt))}</p>${bad.hour !== hot.hour ? `<p>${esc(t().thermoWrong(say(hot.start), say(bad.start)))}</p>` : ""}${outside ? `<p><b>${esc(t().outsideBan(outside))}</b></p>` : ""}</div>`;
    })()}
    <div class="quote"><b>${t().replayWhat}</b><br>${esc((S.lang === "hi" && m.what_happened_hi) || m.what_happened)} <a href="${esc(m.source_url)}" target="_blank" rel="noopener">${esc(m.source)}</a></div>
    <p class="small" style="margin-top:12px">${t().replayData}</p>`;
}

let draft = null;
function viewSite() {
  const base = S.payload?.site || { name: "", lat: null, lon: null, workload: "heavy", crew: 20, new_workers: 0, new_worker_day: 1, shaded: false, window_start: 6, window_end: 19 };
  draft = draft || { day_wage: S.payload?.day_wage || 600, ...base };
  const d = draft;
  const choice = (k) => `<button type="button" class="choice" data-action="workload" data-v="${k}" aria-pressed="${d.workload === k}"><span><b>${esc(t().workload[k])}</b><small>${esc(t().workloadEg[k])}</small></span></button>`;
  const stepper = (k, min, max, step = 1) => `<div class="stepper"><button type="button" data-action="step" data-k="${k}" data-d="${-step}" data-min="${min}" data-max="${max}" aria-label="−">−</button><output>${d[k]}</output><button type="button" data-action="step" data-k="${k}" data-d="${step}" data-min="${min}" data-max="${max}" aria-label="+">+</button></div>`;
  return `
    <h1 class="view-title">${t().siteTitle}</h1>
    <label class="field"><span>${t().siteName}</span><input id="site-name" value="${esc(d.name)}" maxlength="80"></label>
    <div class="field"><span>${t().siteWhere}</span>
      <div class="ask-form"><input id="site-q" placeholder="${esc(t().siteSearch)}"><button type="button" class="btn ghost" data-action="geocode">🔍</button></div>
      <ul class="results" id="geo-results" hidden></ul>
      <div class="row" style="margin-top:8px"><button type="button" class="btn ghost" data-action="gps">📍 ${t().siteGps}</button></div>
      <p class="small" id="site-pos">${d.lat != null ? `${(+d.lat).toFixed(4)}, ${(+d.lon).toFixed(4)}` : ""}</p>
    </div>
    <div class="field"><span>${t().siteWork}</span><div class="choices">${["light", "moderate", "heavy", "very_heavy"].map(choice).join("")}</div></div>
    <div class="field"><span>${t().siteCrew}</span>${stepper("crew", 1, 500)}</div>
    <div class="field"><span>${t().siteNew}</span>${stepper("new_workers", 0, 200)}</div>
    <div class="field"><span>${t().siteNewDay}</span>${stepper("new_worker_day", 1, 5)}</div>
    <div class="field"><span>${t().siteWage}</span>${stepper("day_wage", 200, 3000, 50)}</div>
    <div class="field"><span>${t().siteShade}</span><div class="choices" style="grid-template-columns:1fr 1fr">
      <button type="button" class="choice" data-action="shade" data-v="0" aria-pressed="${!d.shaded}"><b>☀️ ${t().sun}</b></button>
      <button type="button" class="choice" data-action="shade" data-v="1" aria-pressed="${!!d.shaded}"><b>🏗️ ${t().roof}</b></button></div></div>
    <label class="toggle"><input type="checkbox" id="night" ${d.window_end > 19 ? "checked" : ""}> ${t().siteNight}</label>
    <button class="btn block" data-action="save-site">${t().save}</button>`;
}

function viewAbout() {
  const en = S.lang === "en";
  return `<div class="about">
    <h1 class="view-title">${t().about}</h1>
    <p>${en ? "Heat illness is decided by WBGT, not by the thermometer: humid shade at 33°C can be as dangerous as dry sun at 40°C. Chhaon computes outdoor WBGT for every hour of the day from the site's forecast, with the Liljegren model (the method used to turn weather data into WBGT in heat-stress research)." : "लू का ख़तरा थर्मामीटर से नहीं, WBGT से तय होता है: 33°C की उमस वाली छाँव भी 40°C की सूखी धूप जितनी ख़तरनाक हो सकती है। छाँव हर घंटे का WBGT साइट के पूर्वानुमान से Liljegren मॉडल से निकालता है।"}</p>
    <h3>${en ? "How the plan is made" : "प्लान कैसे बनता है"}</h3>
    <dl>
      <dt>${en ? "Safe minutes per hour" : "हर घंटे के सुरक्षित मिनट"}</dt><dd>${en ? "ACGIH heat-stress screening limits for the crew's workload. New workers get the stricter Action Limit and NIOSH's acclimatisation ramp (20% of a normal day on day 1, +20% a day)." : "काम के हिसाब से ACGIH की सीमाएँ। नए साथियों के लिए सख़्त सीमा और NIOSH का नियम (पहले दिन 20%, फिर हर दिन +20%)।"}</dd>
      <dt>${en ? "Keep the pay, move the heat" : "मज़दूरी बचे, गर्मी हटे"}</dt><dd>${en ? "Normal 9-to-6 hours stay where they are safe; unsafe minutes move to the coolest hours of the allowed window, so the crew keeps as much paid work as the heat allows." : "9 से 6 के सुरक्षित घंटे वहीं रहते हैं; ख़तरनाक मिनट सबसे ठंडे घंटों में चले जाते हैं।"}</dd>
      <dt>${en ? "When someone is unwell" : "तबीयत ख़राब हो तो"}</dt><dd>${en ? "Triage and first aid follow India's National Action Plan on Heat Related Illnesses (NCDC, Ministry of Health). Anything not clearly better escalates." : "भारत की राष्ट्रीय कार्य योजना (NCDC, स्वास्थ्य मंत्रालय) के अनुसार। हालत साफ़ बेहतर न हो तो आगे बढ़ाया जाता है।"}</dd>
      <dt>${en ? "What the AI does" : "AI क्या करता है"}</dt><dd>${en ? "It answers questions in Hindi or English by calling the planner as a tool. It never makes a safety decision: the numbers and rules are code, tested." : "सवालों का जवाब प्लानर से हिसाब करके देता है। सुरक्षा का फ़ैसला कोड करता है, AI नहीं।"}</dd>
    </dl>
    <h3>${en ? "Limits" : "सीमाएँ"}</h3>
    <p>${en ? "Forecasts are for the area, not a single site; a WBGT meter on site is better. The table is a screening tool, not a medical device. In an emergency, call 108." : "पूर्वानुमान इलाके का है, साइट का नहीं; साइट पर WBGT मीटर बेहतर है। यह मेडिकल उपकरण नहीं। इमरजेंसी में 108 पर कॉल करें।"}</p>
    <p class="small">${en ? "Weather: Open-Meteo (forecast) and ERA5 via Open-Meteo (replays)." : "मौसम: Open-Meteo और ERA5।"}</p>
  </div>`;
}

// ---------------- render & routing ----------------
function render() {
  const app = document.getElementById("root");
  const parts = location.hash.slice(2).split("/");
  const route = parts[0] || (S.siteId ? "today" : "welcome");
  app.innerHTML = shell();
  document.documentElement.lang = S.lang === "hi" ? "hi" : "en";
  const main = $("#main");
  let html = "";
  if (!S.siteId && !["site", "about", "replay"].includes(route)) html = viewWelcome();
  else if (route === "today") html = viewToday();
  else if (route === "unwell") html = viewUnwell();
  else if (route === "incident") html = viewIncident();
  else if (route === "ask") html = viewAsk();
  else if (route === "replay") html = parts[1] ? viewReplay(parts[1]) : viewReplayList();
  else if (route === "site") html = viewSite();
  else if (route === "about") html = viewAbout();
  else html = S.siteId ? viewToday() : viewWelcome();
  main.innerHTML = html;
}

function clearTimers() { S.timers.forEach(clearInterval); S.timers = []; }

// ---------------- announcements: keep running on every tab ----------------
// The feed (written by the Lambda that EventBridge Scheduler fires) is polled while
// announcements are on, whatever screen is open. If the network drops, today's audio was
// cached at publish time and a local clock plays each break anyway.
const dayKey = () => `${S.siteId}.${istDate()}`;
function istDate() { return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date()); }
function nextAnnouncement() {
  const n = istNow();
  const evs = S.dayAudio?.events || (S.day === "today" ? S.payload?.plan?.events : null) || [];
  const e = evs.find((x) => x.at > n.hhmm);
  return e ? `${say(e.at)} · ${t().kinds[e.kind] || ""}` : "";
}
function startAnnouncer() {
  if (!S.feedTimer) S.feedTimer = setInterval(loadFeed, 10000);
  if (!S.tickTimer) S.tickTimer = setInterval(localTick, 5000);
  if (!S.dayAudio) S.dayAudio = store.get(`audio.${dayKey()}`);
}
function localTick() {
  if (!S.speaker || !S.dayAudio) return;
  const n = istNow();
  for (const e of S.dayAudio.events) {
    const k = `${istDate()}|${e.at}|${e.kind}`;
    const late = n.mins - toMins(e.at);
    // play at the minute it is due from the day's cached audio; the Scheduler-fired Lambda posts
    // the same break to the feed within the minute, which covers phones without the audio
    if (late >= 0 && late < 3 && !S.played.has(k)) { S.played.add(k); play(e.audio, k); }
  }
  const bar = $(".speakerbar");
  if (bar) bar.textContent = t().speakerBar(nextAnnouncement()); // don't re-render: it would clear typed input
}
async function cacheAudio(urls) {
  try { const c = await caches.open("chhaon-audio-v1"); await Promise.all(urls.map((u) => c.match(u).then((hit) => hit || c.add(u)).catch(() => {}))); } catch {}
}
// An open case is watched from every screen: when the re-check question comes, a banner,
// a chime and a vibration bring the supervisor back to it.
function watchIncident(id) { store.set("open-incident", id); startIncidentWatch(); }
function startIncidentWatch() {
  if (S.incidentTimer || !store.get("open-incident")) return;
  S.incidentTimer = setInterval(async () => {
    const id = store.get("open-incident");
    if (!id) { clearInterval(S.incidentTimer); S.incidentTimer = null; return; }
    if (location.hash.startsWith(`#/incident/${id}`)) return; // that page polls itself
    try {
      const inc = await api(`/incidents/${id}`);
      if (["resolved", "handed_over"].includes(inc.status)) { store.del("open-incident"); S.attention = null; render(); return; }
      const key = inc.pending ? `${id}|${inc.pending.asked_at}` : null;
      if (key && S.attention !== key) {
        S.attention = key; chime(); try { navigator.vibrate?.([300, 150, 300]); } catch {}
        render();
      } else if (!key && S.attention) { S.attention = null; render(); }
    } catch {}
  }, 5000);
}

async function flushQueued() {
  const q = store.get("queue.incidents", []);
  if (!q.length) return;
  const left = [];
  for (const item of q) {
    try { await api(`/sites/${item.site}/incidents`, { body: item.body }); } catch { left.push(item); }
  }
  store.set("queue.incidents", left);
  if (left.length < q.length) toast(t().queuedSent, 5000);
}

async function onRoute() {
  clearTimers();
  const parts = location.hash.slice(2).split("/");
  const route = parts[0] || (S.siteId ? "today" : "welcome");
  if (route !== "site") draft = null;
  render();
  window.scrollTo(0, 0);
  if (S.speaker) startAnnouncer();
  startIncidentWatch();
  if (route === "incident" && parts[1] && parts[1] !== "local" && S.attention?.startsWith(parts[1])) S.attention = null;
  if (route === "today" && S.siteId) {
    await loadPlan();
    await loadFeed();
    if (!S.speaker) S.timers.push(setInterval(loadFeed, 10000));
    S.timers.push(setInterval(() => { if (location.hash.startsWith("#/today")) render(); }, 30000));
  } else if (route === "incident" && parts[1] === "local") {
    if (!S.incident?.local) location.hash = "#/unwell";
  } else if (route === "incident" && parts[1]) {
    await loadIncident(parts[1]);
    S.timers.push(setInterval(() => loadIncident(parts[1]), 3000));
  } else if (route === "replay") {
    if (parts[1]) {
      if (!replayData[parts[1]]) { try { replayData[parts[1]] = await api(`/replay/${parts[1]}`); } catch (e) { return showError(e); } }
    } else if (!replayList) {
      try { replayList = (await api("/replays")).items; } catch (e) { return showError(e); }
    }
    render();
  } else if (route === "site" && S.siteId && !S.payload) {
    await loadPlan();
  }
}

function showError(e) {
  const main = $("#main");
  if (main) main.innerHTML = `<div class="err"><b>${t().error}</b><p>${esc(e.message)}</p><button class="btn" data-action="retry">${t().retry}</button></div>`;
}

async function loadPlan() {
  const key = `plan.${S.siteId}.${S.day}`;
  try {
    S.payload = await api(`/sites/${S.siteId}/plan?day=${S.day}`);
    if (S.day === "today") { S.speaker = !!store.get(`speaker.${S.siteId}.${S.payload.date}`); if (S.speaker) startAnnouncer(); }
    store.set(key, S.payload);
  } catch (e) {
    if (e.status === 404) { store.del("site"); S.siteId = null; location.hash = "#/welcome"; return; }
    const cached = store.get(key);
    if (cached) S.payload = cached; else return showError(e);
  }
  render();
}

async function loadFeed() {
  if (!S.siteId) return;
  try {
    const { items } = await api(`/sites/${S.siteId}/feed`);
    const fresh = items.filter((f) => !S.lastFeedTs || f.ts > S.lastFeedTs);
    if (S.lastFeedTs && (S.speaker || S.expectTest)) {
      const ann = fresh.filter((f) => f.type === "announcement" && (S.speaker || f.kind === "test")).pop();
      if (ann?.kind === "test") S.expectTest = false;
      if (ann) {
        const k = `${ann.date || istDate()}|${ann.at}|${ann.kind}`;
        if (!S.played.has(k)) { S.played.add(k); play(ann.audio?.[ann.lang] || Object.values(ann.audio || {})[0], k); }
      }
    }
    if (items.length) S.lastFeedTs = items[items.length - 1].ts;
    else if (!S.lastFeedTs) S.lastFeedTs = new Date(0).toISOString();
    const changed = fresh.length > 0 || S.feed.length !== items.length;
    S.feed = items;
    if (changed && location.hash.startsWith("#/today")) render();
    flushQueued();
  } catch {}
}

async function loadIncident(id) {
  try {
    S.incident = await api(`/incidents/${id}`);
    if (!["resolved", "handed_over"].includes(S.incident.status)) watchIncident(id);
    else if (store.get("open-incident") === id) store.del("open-incident");
    render();
    if (["resolved", "handed_over", "escalated"].includes(S.incident.status)) clearTimers();
  } catch (e) { showError(e); }
}

// ---------------- actions ----------------
const actions = {
  async lang() { S.lang = S.lang === "hi" ? "en" : "hi"; store.set("lang", S.lang); render(); },
  async demo(btn) {
    btn.disabled = true;
    try { const r = await api("/demo", { body: {} }); S.siteId = r.site_id; store.set("site", r.site_id); S.payload = null; location.hash = "#/today"; }
    catch (e) { toast(e.message); btn.disabled = false; }
  },
  async day(btn) { S.day = btn.dataset.day; S.payload = null; render(); await loadPlan(); },
  async "set-work"(btn) {
    // the task mix changes day to day (ढलाई, चिनाई, सरिया): one tap re-plans for today's work
    if (!S.payload || S.payload.site.workload === btn.dataset.v) return;
    btn.disabled = true;
    try {
      await api(`/sites/${S.siteId}`, { method: "PUT", body: { workload: btn.dataset.v } });
      S.payload = null; render(); await loadPlan();
      if (S.speaker && S.day === "today") actions["speaker-on"]({ disabled: false });
    } catch (e) { toast(e.message); btn.disabled = false; }
  },
  "wbgt-help"() { const el = $("#wbgt-help"); if (el) el.hidden = !el.hidden; },
  async "speaker-on"(btn) {
    unlockAudio();
    btn.disabled = true;
    try {
      const r = await api(`/sites/${S.siteId}/publish`, { body: { day: "today" }, timeout: 40000 });
      S.speaker = true; store.set(`speaker.${S.siteId}.${S.payload.date}`, true);
      if (r.events?.length) { S.dayAudio = { events: r.events }; store.set(`audio.${dayKey()}`, S.dayAudio); cacheAudio([...new Set(r.events.map((e) => e.audio))]); }
      startAnnouncer();
      keepAwake();
      toast(t().speakerOn(r.schedules));
      render();
    } catch (e) { toast(e.message); btn.disabled = false; }
  },
  async "test-announce"(btn) {
    unlockAudio();
    S.expectTest = true; keepAwake();
    btn.disabled = true;
    try { const r = await api(`/sites/${S.siteId}/test-announcement`, { body: {} }); toast(t().testQueued(fmtTime(r.fires_at)), 6000); }
    catch (e) { toast(e.message); }
    btn.disabled = false;
    render();
  },
  async preview(btn) {
    unlockAudio();
    btn.disabled = true;
    try { const r = await api(`/sites/${S.siteId}/preview`, { body: { kind: btn.dataset.kind, minutes: +btn.dataset.minutes || 15, until: btn.dataset.until || undefined, lang: S.payload?.site?.lang || S.lang } }); play(r.audio); }
    catch (e) { toast(e.message); }
    btn.disabled = false;
  },
  play(btn) { unlockAudio(); play(btn.dataset.src); },
  sym(btn) { const k = btn.dataset.sym; S.selected.has(k) ? S.selected.delete(k) : S.selected.add(k); btn.setAttribute("aria-pressed", S.selected.has(k)); },
  async "start-incident"(btn) {
    if (!S.selected.size) return toast(t().pickOne);
    btn.disabled = true;
    // one id per report, so a retry (or the offline queue) can never create a second case or email
    const client_id = (crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`).slice(0, 40);
    const body = { symptoms: [...S.selected], worker: $("#worker")?.value || undefined, lang: S.lang, client_id };
    try {
      const inc = await api(`/sites/${S.siteId}/incidents`, { body, timeout: 8000 });
      S.selected.clear(); S.incident = inc; watchIncident(inc.id);
      location.hash = `#/incident/${inc.id}`;
    } catch (e) {
      if (e.status && e.status < 500) { toast(e.message); btn.disabled = false; return; }
      // no network: the same national first-aid steps, from the copy in protocol.js; report later
      const level = classifyLocal(body.symptoms);
      store.set("queue.incidents", [...store.get("queue.incidents", []), { site: S.siteId, body }]);
      S.selected.clear();
      S.incident = { id: "local", local: true, level, status: "open", worker: body.worker || (S.lang === "hi" ? "साथी" : "Worker"), symptoms: body.symptoms, guidance: guidanceLocal(level, S.lang), hospitals: [], pending: null, timeline: [{ t: new Date().toISOString(), kind: "reported", text: body.symptoms.join(", ") }] };
      location.hash = "#/incident/local";
    }
  },
  async brief(btn) {
    btn.disabled = true;
    try {
      const r = await api(`/sites/${S.siteId}/brief`, { body: { day: S.day, lang: S.payload?.site?.lang || "hi" }, timeout: 30000 });
      const url = new URL(r.audio, location.origin).href;
      let shared = false;
      try {
        const blob = await (await fetch(url)).blob();
        const file = new File([blob], `chhaon-${r.date}.mp3`, { type: "audio/mpeg" });
        if (navigator.canShare?.({ files: [file] })) { await navigator.share({ files: [file], text: r.text }); shared = true; }
      } catch (e) { if (e.name === "AbortError") shared = true; }
      if (!shared) { play(r.audio); window.open(`https://wa.me/?text=${encodeURIComponent(`${r.text}\n🔊 ${url}`)}`, "_blank", "noopener"); }
      toast(t().briefReady);
    } catch (e) { toast(e.message); }
    btn.disabled = false;
  },
  async escalate(btn) {
    btn.disabled = true;
    try { await api(`/incidents/${S.incident.id}/escalate`, { body: {} }); await loadIncident(S.incident.id); }
    catch (e) { toast(e.message); btn.disabled = false; }
  },
  async answer(btn) {
    btn.disabled = true;
    try { await api(`/incidents/${S.incident.id}/answer`, { body: { answer: btn.dataset.answer } }); await loadIncident(S.incident.id); }
    catch (e) { toast(e.message); btn.disabled = false; }
  },
  chip(btn) { const q = $("#q"); if (q) { q.value = btn.textContent; askNow(q.value); } },
  async mic(btn) {
    if (S.listening) { S.listening.stop(); return; }
    // Amazon Transcribe streaming (hi-IN) first; the browser's own recogniser if that fails
    try {
      const signed = await api("/listen", { body: { lang: S.lang }, timeout: 8000 });
      btn.classList.add("on");
      toast(t().askListening, 2500);
      S.listening = await listen(signed, (text) => { const q = $("#q"); if (q) q.value = text; }, (text) => {
        S.listening = null; $(".mic")?.classList.remove("on");
        if (text) askNow(text, "transcribe"); else toast(t().askHeardNothing);
      });
      return;
    } catch (e) { S.listening = null; btn.classList.remove("on"); }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return toast(t().error);
    const rec = new SR();
    rec.lang = S.lang === "hi" ? "hi-IN" : "en-IN";
    rec.onresult = (e) => { const text = e.results[0][0].transcript; const q = $("#q"); if (q) q.value = text; askNow(text); };
    rec.onerror = () => toast(t().error);
    rec.start();
  },
  async speak(btn) {
    const x = S.qa[+btn.dataset.i];
    if (!x?.a) return;
    btn.disabled = true;
    // first aid is spoken from the national guideline's own words, not the model's paraphrase
    const text = x.a.protocol ? [x.a.protocol.title, ...x.a.protocol.steps].join(" ") : x.a.answer;
    try { const r = await api(`/sites/${S.siteId}/speak`, { body: { text, lang: x.a.lang } }); play(r.audio); }
    catch (e) { toast(e.message); }
    btn.disabled = false;
  },
  workload(btn) { draft.workload = btn.dataset.v; render(); },
  shade(btn) { draft.shaded = btn.dataset.v === "1"; render(); },
  step(btn) { const k = btn.dataset.k; draft[k] = Math.max(+btn.dataset.min, Math.min(+btn.dataset.max, (+draft[k] || 0) + +btn.dataset.d)); keepDraftInputs(); render(); },
  async geocode() {
    keepDraftInputs();
    const q = $("#site-q")?.value.trim();
    if (!q || q.length < 3) return;
    try {
      const { results } = await api(`/geocode?q=${encodeURIComponent(q)}`);
      const ul = $("#geo-results");
      ul.hidden = false;
      ul.innerHTML = results.length ? results.map((r, i) => `<li><button type="button" data-action="pick" data-lat="${r.lat}" data-lon="${r.lon}" data-name="${esc(r.name)}">${esc(r.name)}<br><span class="small">${esc(r.address || "")}</span></button></li>`).join("") : `<li class="small" style="padding:10px">—</li>`;
    } catch (e) { toast(e.message); }
  },
  pick(btn) { keepDraftInputs(); draft.lat = +btn.dataset.lat; draft.lon = +btn.dataset.lon; if (!draft.name) draft.name = btn.dataset.name; render(); },
  gps() {
    keepDraftInputs();
    if (!navigator.geolocation) return toast(t().error);
    navigator.geolocation.getCurrentPosition((p) => { draft.lat = +p.coords.latitude.toFixed(5); draft.lon = +p.coords.longitude.toFixed(5); render(); }, () => toast(t().error), { enableHighAccuracy: true, timeout: 10000 });
  },
  async "save-site"(btn) {
    keepDraftInputs();
    if (draft.lat == null) return toast(t().siteWhere);
    draft.window_start = $("#night")?.checked ? 5 : 6;
    draft.window_end = $("#night")?.checked ? 22 : 19;
    btn.disabled = true;
    try {
      const body = { name: draft.name || (S.lang === "hi" ? "मेरी साइट" : "My site"), lat: draft.lat, lon: draft.lon, workload: draft.workload, crew: draft.crew, new_workers: draft.new_workers, new_worker_day: draft.new_worker_day, day_wage: draft.day_wage, shaded: !!draft.shaded, window_start: draft.window_start, window_end: draft.window_end, lang: S.lang };
      const r = S.siteId ? await api(`/sites/${S.siteId}`, { method: "PUT", body }) : await api("/sites", { body });
      S.siteId = r.site_id; store.set("site", r.site_id); S.payload = null; draft = null;
      toast(t().saved);
      location.hash = "#/today";
    } catch (e) { toast(e.message); btn.disabled = false; }
  },
  retry() { onRoute(); },
};

function keepDraftInputs() {
  if (!draft) return;
  const n = $("#site-name"); if (n) draft.name = n.value;
  const night = $("#night"); if (night) draft.window_end = night.checked ? 22 : 19;
}

async function askNow(question, via) {
  question = (question || "").trim();
  if (question.length < 2) return;
  const q = $("#q"); if (q) q.value = "";
  const entry = { q: question, a: null, via };
  S.qa.push(entry);
  render();
  try { entry.a = await api("/ask", { body: { site_id: S.siteId, question }, timeout: 40000 }); }
  catch (e) { entry.a = { answer: `${t().error}: ${e.message}`, tools_used: [] }; }
  if (location.hash.startsWith("#/ask")) render();
}

document.addEventListener("click", (ev) => {
  const el = ev.target.closest("[data-action]");
  if (!el || el.tagName === "FORM") return;
  const fn = actions[el.dataset.action];
  if (fn) { ev.preventDefault(); fn(el); }
});
document.addEventListener("submit", (ev) => {
  if (ev.target.dataset.action === "ask") { ev.preventDefault(); const q = $("#q"); askNow(q.value); q.value = ""; }
});
window.addEventListener("hashchange", onRoute);
window.addEventListener("online", () => { S.offline = false; flushQueued(); onRoute(); });
window.addEventListener("offline", () => { S.offline = true; render(); });

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
onRoute();
