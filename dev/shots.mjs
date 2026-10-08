// Screenshot the main screens at phone and desktop sizes against the local server.
import { chromium } from "playwright";

const base = process.env.BASE || "http://localhost:8787";
const out = process.env.OUT || "/tmp/claude-0/shots";
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined });
const errors = [];

async function phone(lang = "hi") {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, locale: lang === "hi" ? "hi-IN" : "en-IN" });
  const page = await ctx.newPage();
  page.on("console", (m) => m.type() === "error" && errors.push(`[${lang}] ${m.text()}`));
  page.on("pageerror", (e) => errors.push(`[${lang}] ${e.message}`));
  await page.addInitScript((l) => localStorage.setItem("chhaon.lang", JSON.stringify(l)), lang);
  return { ctx, page };
}

const { page } = await phone("hi");
await page.goto(base + "/");
await page.waitForTimeout(600);
await page.screenshot({ path: `${out}/01-welcome-hi.png`, fullPage: true });
await page.click("[data-action=demo]");
await page.waitForSelector(".now", { timeout: 10000 });
await page.waitForTimeout(800);
await page.screenshot({ path: `${out}/02-today-hi.png`, fullPage: true });
await page.click("[data-action=day][data-day=tomorrow]");
await page.waitForTimeout(800);
await page.screenshot({ path: `${out}/03-tomorrow-hi.png`, fullPage: true });
await page.click("[data-action=day][data-day=today]");
await page.waitForTimeout(500);
await page.click("[data-action=test-announce]");
await page.waitForTimeout(500);
await page.goto(base + "/#/unwell");
await page.waitForSelector(".syms");
await page.click("[data-sym=dizzy]");
await page.click("[data-sym=vomiting]");
await page.screenshot({ path: `${out}/04-unwell-hi.png`, fullPage: true });
await page.click("[data-action=start-incident]");
await page.waitForSelector(".level", { timeout: 10000 });
await page.waitForTimeout(1500);
await page.screenshot({ path: `${out}/05-incident-amber-hi.png`, fullPage: true });
await page.waitForSelector("[data-answer=worse]", { timeout: 40000 });
await page.screenshot({ path: `${out}/06-incident-recheck-hi.png`, fullPage: true });
await page.click("[data-answer=worse]");
await page.waitForSelector(".level.red", { timeout: 15000 });
await page.waitForTimeout(3500);
await page.screenshot({ path: `${out}/07-incident-red-hi.png`, fullPage: true });
await page.goto(base + "/#/ask");
await page.waitForSelector(".chips");
await page.click(".chips button");
await page.waitForSelector(".qa .ev", { timeout: 15000 });
await page.screenshot({ path: `${out}/08-ask-hi.png`, fullPage: true });
await page.goto(base + "/#/replay/rourkela-2024-05-30");
await page.waitForSelector(".quote", { timeout: 10000 });
await page.screenshot({ path: `${out}/09-replay-hi.png`, fullPage: true });
await page.goto(base + "/#/site");
await page.waitForSelector(".choices");
await page.screenshot({ path: `${out}/10-site-hi.png`, fullPage: true });
await page.goto(base + "/#/today");
await page.waitForTimeout(66000); // the 1-minute test announcement should arrive
await page.screenshot({ path: `${out}/11-today-after-test-hi.png`, fullPage: true });

const desk = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const dp = await desk.newPage();
dp.on("pageerror", (e) => errors.push(`[desktop] ${e.message}`));
await dp.addInitScript(() => localStorage.setItem("chhaon.lang", JSON.stringify("en")));
await dp.goto(base + "/");
await dp.click("[data-action=demo]");
await dp.waitForSelector(".now", { timeout: 10000 });
await dp.waitForTimeout(800);
await dp.screenshot({ path: `${out}/12-desktop-en.png` });

console.log("errors:", JSON.stringify(errors, null, 1));
await browser.close();
