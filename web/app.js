import { STR } from "./i18n.js";

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
const fmtTime = (iso) => new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(iso));

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
function play(url) {
  if (!url) return;
  player.src = url;
  player.play().catch(() => toast(t().listen + " ▶"));
}
async function keepAwake() {
  try { if ("wakeLock" in navigator && !S.wakeLock) S.wakeLock = await navigator.wakeLock.request("screen"); } catch {}
}
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && S.speaker) { S.wakeLock = null; keepAwake(); } });

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
      <main id="main" tabindex="-1"></main>
      ${S.siteId ? `<nav class="tabs" aria-label="Main">
        ${tab("today", "today", I.today, t().tabToday)}
        ${tab("unwell", "unwell", I.unwell, t().tabUnwell, "urgent")}
        ${tab("ask", "ask", I.ask, t().tabAsk)}
        ${tab("replay", "replay", I.replay, t().tabReplay)}
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
      <li><div><b>${en ? "Ask in Hindi" : "हिंदी में पूछिए"}</b><span>${en ? "'कल दोपहर 2 बजे ढलाई कर सकते हैं?' Bedrock answers using the planner as a tool." : "'कल दोपहर 2 बजे ढलाई कर सकते हैं?' Bedrock प्लानर से हिसाब करके बताता है।"}</span> <a href="#/ask">${en ? "Open" : "खोलिए"}</a></div></li>
      <li><div><b>${en ? "Replay 30 May 2024" : "30 मई 2024 दोहराइए"}</b><span>${en ? "Rourkela, the day ten heatstroke deaths were reported. What Chhaon would have said with that day's weather." : "राउरकेला, जिस दिन लू से दस मौतें दर्ज हुईं। उस दिन के मौसम पर छाँव क्या कहता।"}</span> <a href="#/replay/rourkela-2024-05-30">${en ? "Open" : "खोलिए"}</a></div></li>
    </ol>
    <dl class="aws">
      <dt>Lambda</dt><dd>${en ? "WBGT (Liljegren) and the shift planner, deterministic and unit-tested" : "WBGT (Liljegren) और शिफ़्ट प्लानर"}</dd>
      <dt>EventBridge Scheduler</dt><dd>${en ? "one timer per break, deleted after it fires" : "हर ब्रेक का अपना टाइमर"}</dd>
      <dt>Step Functions</dt><dd>${en ? "heat-illness protocol: waits, re-checks, escalation" : "बीमारी प्रोटोकॉल: इंतज़ार, दोबारा जाँच, आगे सूचना"}</dd>
      <dt>Polly · Bedrock · Location</dt><dd>${en ? "Hindi voice, the assistant, nearest hospitals" : "हिंदी आवाज़, सहायक, नज़दीकी अस्पताल"}</dd>
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
  if (!work.length) { status = t().nowNoWork; band = "stop"; }
  else if (n.hhmm < work[0].start) { status = t().nowBefore(p.crew.first_start); band = "shade"; }
  else if (n.mins >= toMins(p.crew.last_end)) { status = t().nowAfter; band = "shade"; }
  else if (cur && cur.status === "work") {
    if (n.m < cur.work_minutes) { status = t().nowWork(cur.work_minutes, cur.rest_minutes); sub = t().nowWorkLeft(cur.work_minutes - n.m); }
    else { status = t().nowRest(`${String(n.h + 1).padStart(2, "0")}:00`); }
  } else if (cur && cur.status === "stop") {
    const until = (p.crew.stop_windows.find(([a, b]) => a <= n.hhmm && n.hhmm < b) || [null, nextEv?.at || "--"])[1];
    status = t().nowStop(until);
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
    return `<div class="h"><span class="w">${Math.round(h.wbgt)}</span><div class="bar ${cls} ${h.hour === nowH ? "now-col" : ""}" title="${esc(label)}" aria-label="${esc(label)}"><div class="fill" style="height:${h.status === "stop" ? 0 : pct}%"></div></div><span class="t">${h.hour}</span></div>`;
  }).join("")}</div>`;
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
    ${ns.nextEv ? `<p class="next">${t().next(ns.nextEv.at, t().kinds[ns.nextEv.kind], toMins(ns.nextEv.at) - ns.n.mins)}</p>` : ""}` : `
    <section class="now ${p.verdict === "normal" ? "safe" : p.verdict === "adjusted" ? "caution" : "stop"}">
      <p class="status">${p.crew.first_start ? t().nowBefore(p.crew.first_start) : t().nowNoWork}</p>
      <p class="sub">${p.crew.stop_windows.map(([a, b]) => t().nowStop(b).replace(b, `${a}–${b}`)).join(" · ") || t().impactNormal}</p>
      <div class="wbgt"><b>${p.peak_wbgt?.toFixed(1) ?? "–"}°</b><span>${t().wbgtLabel}<br>${S.lang === "hi" ? "सबसे ज़्यादा" : "peak"} ${p.peak_time ?? ""}</span></div>
    </section>`;

  const newbie = p.new_workers && site.new_workers > 0 ? (() => {
    const w = p.new_workers.hours.filter((h) => h.work_minutes > 0);
    const when = w.length ? w.map((h) => h.start).join(", ") : "–";
    return `<p class="note">${esc(t().newWorkers(site.new_workers, site.new_worker_day || 1, p.new_workers.planned_minutes, when))}</p>`;
  })() : "";

  const impact = p.verdict === "normal" ? t().impactNormal : t().impact(p.unsafe_hours_avoided, fmtMins(p.crew.planned_minutes), fmtMins(p.crew.target_minutes));
  const feedItems = S.feed.slice(-6).reverse();
  return `
    <div class="site-head">
      <div><h2>${esc(site.name)}</h2><div class="meta">${esc(t().workload[site.workload])}, ${site.crew} ${t().crew}${site.shaded ? `, ${t().roof}` : ""}</div></div>
      <div class="daypick" role="group" aria-label="Day">
        <button data-action="day" data-day="today" aria-pressed="${isToday}">${t().today}</button>
        <button data-action="day" data-day="tomorrow" aria-pressed="${!isToday}">${t().tomorrow}</button>
      </div>
    </div>
    ${nowCard}
    <section class="plan">
      <h3>${isToday ? t().planTitle : t().planTitleTomorrow}</h3>
      <div class="strip-label">${t().normalRow}</div>
      ${stripHtml(p.crew.hours, "normal")}
      <div class="strip-label">${t().chhaonRow}</div>
      ${stripHtml(p.crew.hours, "plan", isToday ? ns.n.h : -1)}
      <p class="legend">${t().legend}</p>
      <p class="impact">${esc(impact)}</p>
      ${p.crew.shortfall_minutes > 0 ? `<p class="note">${esc(t().shortfall(p.crew.shortfall_minutes))}</p>` : ""}
      ${newbie}
    </section>
    ${isToday ? `<section class="card">
      <h3>${t().speaker}</h3>
      <p>${S.speaker ? esc(t().speakerOn(p.events.filter((e) => e.at > ns.n.hhmm).length)) : t().speakerOff}</p>
      <div class="row">
        ${S.speaker ? "" : `<button class="btn" data-action="speaker-on">${t().speakerStart}</button>`}
        <button class="btn ghost" data-action="test-announce">${t().speakerTest}</button>
        ${ns.nextEv ? `<button class="btn ghost" data-action="preview" data-kind="${ns.nextEv.kind}" data-minutes="${ns.nextEv.minutes}" data-until="${ns.nextEv.until || ""}">${I.play} ${t().listen}</button>` : ""}
      </div>
      <ul class="feed">${feedItems.length ? feedItems.map(feedItem).join("") : `<li><span class="txt small">${t().feedEmpty}</span></li>`}</ul>
    </section>` : ""}`;
}

function feedItem(f) {
  if (f.type === "announcement") {
    const audio = f.audio?.[S.lang] || Object.values(f.audio || {})[0];
    return `<li><span class="when">${fmtTime(f.ts)}</span><span class="txt">${esc(f.text?.[S.lang] || "")}</span>${audio ? `<button class="icon-btn" data-action="play" data-src="${esc(audio)}" aria-label="${t().listen}">${I.play}</button>` : ""}</li>`;
  }
  if (f.type === "incident" || f.type === "alert") {
    return `<li class="alert"><span class="when">${fmtTime(f.ts)}</span><a class="txt" href="#/incident/${esc(f.incident_id)}">${f.type === "alert" ? "108 · " : ""}${esc(f.worker || "")} ${esc(t().status[f.type === "alert" ? "emergency" : "open"])}</a></li>`;
  }
  return "";
}

function viewUnwell() {
  const tile = (k, red) => `<button class="sym ${red ? "red" : ""}" data-action="sym" data-sym="${k}" aria-pressed="${S.selected.has(k)}"><span class="e" aria-hidden="true">${SYM_EMOJI[k]}</span>${esc(t().symptoms[k])}</button>`;
  return `
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
  return `
    <section class="level ${lvl}">
      <h2>${esc(g.title)}</h2>
      <div>${esc(inc.worker)}: ${inc.symptoms.map((s) => esc(t().symptoms[s] || s)).join(", ")}</div>
      <div><b>${esc(t().status[inc.status] || inc.status)}</b></div>
      ${g.call_108 ? `<a class="btn block" href="tel:108">📞 ${t().call108}</a>` : ""}
    </section>
    ${q ? `<section class="ask-card" aria-live="assertive">
      <p>${esc(inc.timeline.filter((x) => x.kind === "question").slice(-1)[0]?.text || "")}</p>
      <div class="answers">${q.options.map((o) => `<button class="btn ${o === "worse" ? "red" : o === "better" ? "" : "ghost"} block" data-action="answer" data-answer="${o}">${esc(t().answers[o])}</button>`).join("")}</div>
    </section>` : ""}
    <h3 style="margin-top:20px">${t().steps}</h3>
    <ol class="steps">${g.steps.map((s) => `<li><span>${esc(s)}</span></li>`).join("")}</ol>
    ${inc.hospitals?.length ? `<h3 style="margin-top:20px">${t().hospitals}</h3><ul class="hosp">${inc.hospitals.map((h) => `<li><b>${esc(h.name)}</b><span class="small">${esc(h.address || "")}${h.distance_m ? ` · ${(h.distance_m / 1000).toFixed(1)} km` : ""}</span><div class="row">${h.phone ? `<a href="tel:${esc(h.phone)}">📞 ${esc(h.phone)}</a>` : ""}<a href="https://www.google.com/maps/dir/?api=1&destination=${h.lat},${h.lon}" target="_blank" rel="noopener">${t().directions}</a></div></li>`).join("")}</ul>` : ""}
    <h3 style="margin-top:20px">${t().timeline}</h3>
    <ul class="timeline">${inc.timeline.map((x) => `<li><time>${fmtTime(x.t)}</time>${esc(x.kind === "answer" ? t().answers[x.text] || x.text : x.kind === "reported" ? x.text.split(", ").map((s) => t().symptoms[s] || s).join(", ") : x.text)}</li>`).join("")}</ul>
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
      ${("webkitSpeechRecognition" in window || "SpeechRecognition" in window) ? `<button type="button" class="icon-btn" style="width:52px;height:52px" data-action="mic" aria-label="${t().askMic}">🎤</button>` : ""}
      <button class="btn" type="submit">${t().askSend}</button>
    </form>
    <div class="qa">${S.qa.map((x, i) => `
      <p class="q">${esc(x.q)}</p>
      <div class="a">${x.a ? esc(x.a.answer) : esc(t().askThinking)}</div>
      ${x.a ? `<div class="ev">${x.a.model_unavailable ? esc(t().askFallback) : esc(t().askEvidence((x.a.tools_used || []).join(", ") || "plan"))}${x.a.engine ? ` · ${esc(x.a.engine)}` : ""}</div>
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
  const stops = p.crew.stop_windows.map(([a, b]) => `${a}–${b}`).join(", ") || "–";
  const cols = p.crew.hours.filter((h) => h.status !== "off" || h.in_normal_shift);
  const official = m.official_window ? `<div class="strip-label">${esc(t().replayOfficial(m.official_window[0], m.official_window[1]))}</div>
    <div class="official" style="display:grid;grid-template-columns:repeat(${cols.length},minmax(0,1fr))">${cols.map((h) => `<span style="background:${h.start >= m.official_window[0] && h.start < m.official_window[1] ? "var(--ink)" : "transparent"}"></span>`).join("")}</div>` : "";
  return `
    <a href="#/replay" class="small">${t().replayTitle}</a>
    <h1 class="view-title">${esc(m.place)}<br>${esc(fmtDate(m.date))}</h1>
    <section class="now stop"><p class="status">${esc(t().replayVerdict(stops))}</p>
      <div class="wbgt"><b>${p.peak_wbgt?.toFixed(1)}°</b><span>${t().wbgtLabel}<br>${S.lang === "hi" ? "सबसे ज़्यादा" : "peak"} ${p.peak_time}</span></div></section>
    <section class="plan">
      <div class="strip-label">${t().normalRow}</div>${stripHtml(p.crew.hours, "normal")}
      <div class="strip-label">${t().chhaonRow} (${esc(t().workload[p.workload])})</div>${stripHtml(p.crew.hours, "plan", -1)}
      ${official}
      <p class="legend">${t().legend}</p>
      <p class="impact">${esc(t().impact(p.unsafe_hours_avoided, fmtMins(p.crew.planned_minutes), fmtMins(p.crew.target_minutes)))}</p>
    </section>
    ${(() => {
      const day = p.crew.hours.filter((h) => h.hour >= 6 && h.hour < 19);
      const hot = day.reduce((a, b) => (b.air_temp > a.air_temp ? b : a));
      const bad = day.reduce((a, b) => (b.wbgt > a.wbgt ? b : a));
      const outside = m.official_window ? day.filter((h) => h.status === "stop" && !(h.start >= m.official_window[0] && h.start < m.official_window[1])).length : 0;
      return `<div class="card contrast"><p class="hot">${esc(t().hottestAir(hot.start, hot.air_temp))}</p><p class="bad">${esc(t().mostDangerous(bad.start, bad.wbgt))}</p>${bad.hour !== hot.hour ? `<p>${esc(t().thermoWrong)}</p>` : ""}${outside ? `<p><b>${esc(t().outsideBan(outside))}</b></p>` : ""}</div>`;
    })()}
    <div class="quote"><b>${t().replayWhat}</b><br>${esc(m.what_happened)} <a href="${esc(m.source_url)}" target="_blank" rel="noopener">${esc(m.source)}</a></div>
    <p class="small" style="margin-top:12px">${t().replayData}</p>`;
}

let draft = null;
function viewSite() {
  const base = S.payload?.site || { name: "", lat: null, lon: null, workload: "heavy", crew: 20, new_workers: 0, new_worker_day: 1, shaded: false, window_start: 6, window_end: 19 };
  draft = draft || { ...base };
  const d = draft;
  const choice = (k) => `<button type="button" class="choice" data-action="workload" data-v="${k}" aria-pressed="${d.workload === k}"><span><b>${esc(t().workload[k])}</b><small>${esc(t().workloadEg[k])}</small></span></button>`;
  const stepper = (k, min, max) => `<div class="stepper"><button type="button" data-action="step" data-k="${k}" data-d="-1" data-min="${min}" data-max="${max}" aria-label="−">−</button><output>${d[k]}</output><button type="button" data-action="step" data-k="${k}" data-d="1" data-min="${min}" data-max="${max}" aria-label="+">+</button></div>`;
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

async function onRoute() {
  clearTimers();
  const parts = location.hash.slice(2).split("/");
  const route = parts[0] || (S.siteId ? "today" : "welcome");
  if (route !== "site") draft = null;
  render();
  window.scrollTo(0, 0);
  if (route === "today" && S.siteId) {
    await loadPlan();
    await loadFeed();
    S.timers.push(setInterval(loadFeed, 10000));
    S.timers.push(setInterval(() => { if (location.hash.startsWith("#/today")) render(); }, 30000));
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
    S.speaker = !!store.get(`speaker.${S.siteId}.${S.payload.date}`) && S.day === "today";
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
    if (S.lastFeedTs && S.speaker) {
      const ann = fresh.filter((f) => f.type === "announcement").pop();
      if (ann) play(ann.audio?.[ann.lang] || Object.values(ann.audio || {})[0]);
    }
    if (items.length) S.lastFeedTs = items[items.length - 1].ts;
    else if (!S.lastFeedTs) S.lastFeedTs = new Date(0).toISOString();
    const changed = fresh.length > 0 || S.feed.length !== items.length;
    S.feed = items;
    if (changed && location.hash.startsWith("#/today")) render();
  } catch {}
}

async function loadIncident(id) {
  try {
    S.incident = await api(`/incidents/${id}`);
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
  "wbgt-help"() { const el = $("#wbgt-help"); if (el) el.hidden = !el.hidden; },
  async "speaker-on"(btn) {
    unlockAudio();
    btn.disabled = true;
    try {
      const r = await api(`/sites/${S.siteId}/publish`, { body: { day: "today" } });
      S.speaker = true; store.set(`speaker.${S.siteId}.${S.payload.date}`, true);
      keepAwake();
      toast(t().speakerOn(r.schedules));
      render();
    } catch (e) { toast(e.message); btn.disabled = false; }
  },
  async "test-announce"(btn) {
    unlockAudio();
    S.speaker = true; keepAwake();
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
    try {
      const inc = await api(`/sites/${S.siteId}/incidents`, { body: { symptoms: [...S.selected], worker: $("#worker")?.value || undefined, lang: S.lang } });
      S.selected.clear(); S.incident = inc;
      location.hash = `#/incident/${inc.id}`;
    } catch (e) { toast(e.message); btn.disabled = false; }
  },
  async answer(btn) {
    btn.disabled = true;
    try { await api(`/incidents/${S.incident.id}/answer`, { body: { answer: btn.dataset.answer } }); await loadIncident(S.incident.id); }
    catch (e) { toast(e.message); btn.disabled = false; }
  },
  chip(btn) { const q = $("#q"); if (q) { q.value = btn.textContent; askNow(q.value); } },
  mic() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;
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
    try { const r = await api(`/sites/${S.siteId}/speak`, { body: { text: x.a.answer, lang: x.a.lang } }); play(r.audio); }
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
      const body = { name: draft.name || (S.lang === "hi" ? "मेरी साइट" : "My site"), lat: draft.lat, lon: draft.lon, workload: draft.workload, crew: draft.crew, new_workers: draft.new_workers, new_worker_day: draft.new_worker_day, shaded: !!draft.shaded, window_start: draft.window_start, window_end: draft.window_end, lang: S.lang };
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

async function askNow(question) {
  question = (question || "").trim();
  if (question.length < 2) return;
  const entry = { q: question, a: null };
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
window.addEventListener("online", () => { S.offline = false; onRoute(); });
window.addEventListener("offline", () => { S.offline = true; render(); });

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
onRoute();
