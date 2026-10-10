// README screenshots against the local server (python dev/server.py), with the phone's clock
// set to mid-morning India time so the Today screen shows a working day.
// Run: node dev/doc_screens.mjs   (PLAYWRIGHT=/path/to/playwright/index.mjs if not installed locally)
const pw = await import(process.env.PLAYWRIGHT || "playwright");
const { chromium } = pw.default || pw;
const base = process.env.BASE || "http://localhost:8787";
const out = process.env.OUT || "docs/screens";
const at = process.env.AT || "10:40";
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined });
const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
const when = new Date(`${today}T${at}:00+05:30`);
const errors = [];

async function phone(lang) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.clock.setFixedTime(when);
  page.on("pageerror", (e) => errors.push(`[${lang}] ${e.message}`));
  await page.addInitScript((l) => localStorage.setItem("chhaon.lang", JSON.stringify(l)), lang);
  await page.goto(base + "/");
  await page.click("[data-action=demo]");
  await page.waitForSelector(".now", { timeout: 10000 });
  await page.waitForTimeout(600);
  return page;
}

for (const lang of ["hi", "en"]) {
  const page = await phone(lang);
  await page.screenshot({ path: `${out}/today-${lang}.png` });
  await page.evaluate(() => document.querySelector(".impact")?.scrollIntoView({ block: "start" }));
  await page.waitForTimeout(200);
  await page.screenshot({ path: `${out}/plan-${lang}.png` });
  await page.goto(base + "/#/replay/aurangabad-2024-05-30");
  await page.waitForSelector(".quote", { timeout: 10000 });
  await page.screenshot({ path: `${out}/replay-${lang}.png`, fullPage: true });
  if (lang === "hi") {
    await page.goto(base + "/#/unwell");
    await page.waitForSelector(".syms");
    await page.click("[data-sym=confused]");
    await page.click("[data-action=start-incident]");
    await page.waitForSelector(".level.red", { timeout: 15000 });
    await page.waitForTimeout(2500);
    await page.screenshot({ path: `${out}/emergency-hi.png` });
  }
}
const desk = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const dp = await desk.newPage();
await dp.clock.setFixedTime(when);
await dp.addInitScript(() => localStorage.setItem("chhaon.lang", JSON.stringify("en")));
await dp.goto(base + "/");
await dp.click("[data-action=demo]");
await dp.waitForSelector(".now", { timeout: 10000 });
await dp.waitForTimeout(600);
await dp.screenshot({ path: `${out}/desktop-en.png` });
console.log("errors:", JSON.stringify(errors));
await browser.close();
