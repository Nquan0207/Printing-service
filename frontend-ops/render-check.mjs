import { chromium } from "playwright";

const base = process.env.BASE ?? "http://127.0.0.1:5173";
const browser = await chromium.launch({ channel: "chrome" });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 950 } });
const page = await ctx.newPage();

const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(`PAGEERROR: ${e.message}`));

const shot = (n) => page.screenshot({ path: `/tmp/shot-${n}.png` });

async function signIn(email) {
  await page.goto(base, { waitUntil: "domcontentloaded" });
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: "networkidle" });
  await page.fill('input[type="email"]', email);
  await page.click('button[type="submit"]');
}

// ---------- customer: product detail with image gallery ----------
await signIn("alice@stockroom.local");
await page.waitForURL("**/shop");
await page.waitForSelector(".mantine-Card-root");
console.log("PRODUCT DETAIL");
// open the first card that advertises extra photos
const more = page.locator("text=/\\+\\d+ more photo/").first();
console.log("  cards advertising extra photos:", await page.locator("text=/\\+\\d+ more photo/").count());
await more.click();
await page.waitForSelector(".mantine-Modal-content");
const thumbs = await page.locator(".mantine-Modal-content .thumb").count();
console.log("  images in modal (1 main + thumbs):", thumbs);
const modalText = await page.locator(".mantine-Modal-content").innerText();
console.log("  has description:", /\S{20,}/.test(modalText.split("\n").slice(2).join(" ")));
await shot("detail");
// click the 2nd thumbnail and confirm the main image swaps
const mainBefore = await page.locator(".mantine-Modal-content .thumb img").first().getAttribute("src");
await page.locator(".mantine-Modal-content .thumb").nth(2).click();
const mainAfter = await page.locator(".mantine-Modal-content .thumb img").first().getAttribute("src");
console.log("  thumbnail switches main image:", mainBefore !== mainAfter);
await page.keyboard.press("Escape");

// ---------- admin: edit price_adjustment_jpy ----------
await signIn("admin@stockroom.local");
await page.waitForURL("**/admin");
await page.click("text=Catalog");
await page.waitForSelector("table");
await page.locator("button:has-text('Edit')").first().click();
await page.waitForSelector("text=Size adjustments");
console.log("ADMIN SIZE EDIT");
const adjInputs = page.locator("input").filter({ hasNot: page.locator("[readonly]") });
const labels = await page.locator("text=/ adjustment$/").allTextContents();
console.log("  adjustment fields:", labels.join(", "));
await shot("admin-edit");

// bump the M adjustment by 100 and save
const mField = page.locator("div.mantine-InputWrapper-root", { hasText: "M adjustment" }).locator("input");
const before = await mField.inputValue();
console.log("  M adjustment before:", before);
await mField.fill("");
await mField.type("999");
await page.click("button:has-text('Save')");
await page.waitForSelector("text=updated", { timeout: 10000 });
console.log("  saved (toast shown)");

await browser.close();
console.log(errors.length ? "CONSOLE ERRORS:" : "console errors: none");
errors.slice(0, 6).forEach((e) => console.log("  !", e));
