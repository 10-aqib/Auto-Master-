// End-to-end browser test of the owner console (auth, users, data sources) on a running stack.
// Usage: node tests/e2e/console-flow.mjs   (requires `make dev`, an EMPTY users table, and Playwright)
// Uses fake test identities only. Screenshots go to $E2E_SCREENSHOT_DIR when set.
import { execFileSync } from "node:child_process";
import { createHmac } from "node:crypto";
import { chromium } from "playwright";

const BASE = process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000";
const SHOTS = process.env.E2E_SCREENSHOT_DIR;
const OWNER = { email: "owner@example.test", password: "Owner-Passphrase-For-E2E-1" };
const REVIEWER = { email: "reviewer@example.test", temp: "Temporary-Reviewer-Pass-1", next: "Reviewer-New-Passphrase-2" };

function totp(base32, offsetSteps = 0) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const c of base32.replace(/=+$/, "")) bits += alphabet.indexOf(c).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g).map((b) => parseInt(b, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000) + offsetSteps));
  const h = createHmac("sha1", key).update(counter).digest();
  const o = h[h.length - 1] & 0xf;
  return String((h.readUInt32BE(o) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

let step = 0;
async function check(name, fn) {
  step += 1;
  try {
    await fn();
    console.log(`PASS  ${String(step).padStart(2)} ${name}`);
  } catch (err) {
    console.log(`FAIL  ${String(step).padStart(2)} ${name}\n      ${err.message.split("\n")[0]}`);
    throw err;
  }
}
const shot = async (page, name) => SHOTS && page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
const expectUrl = async (page, path) => page.waitForURL((u) => u.pathname === path, { timeout: 10_000 });

execFileSync(
  "docker",
  ["compose", "exec", "-T", "api", "python", "-m", "webforge_api.cli", "bootstrap-owner",
   "--email", OWNER.email, "--name", "E2E Owner", "--password-stdin"],
  { input: `${OWNER.password}\n`, stdio: ["pipe", "inherit", "inherit"] },
);

const browser = await chromium.launch();
const errors = [];
try {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 860 } });
  const page = await ctx.newPage();
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  let secret = "";
  let recovery = [];

  await check("signed-out visit redirects to /login", async () => {
    await page.goto(`${BASE}/users`);
    await expectUrl(page, "/login");
    await shot(page, "01-login");
  });

  await check("wrong password shows a generic error", async () => {
    await page.getByLabel("Email").fill(OWNER.email);
    await page.getByLabel("Password").fill("definitely-wrong-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.getByRole("alert").filter({ hasText: "Invalid email or password" }).waitFor();
  });

  await check("owner sign-in requires MFA enrolment", async () => {
    await page.getByLabel("Password").fill(OWNER.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expectUrl(page, "/setup/mfa");
  });

  await check("MFA enrolment shows QR, accepts code, shows recovery codes", async () => {
    await page.getByRole("button", { name: "Start setup" }).click();
    await page.getByAltText("QR code for your authenticator app").waitFor();
    await page.getByText("Can’t scan? Enter the key manually").click();
    secret = (await page.locator("details code").innerText()).trim();
    await shot(page, "02-mfa-setup");
    await page.getByLabel("2. Enter the 6-digit code it shows").fill(totp(secret));
    await page.getByRole("button", { name: "Turn on two-factor authentication" }).click();
    const list = page.getByRole("list", { name: "Recovery codes" });
    await list.waitFor();
    recovery = (await list.locator("li").allInnerTexts()).map((s) => s.trim());
    if (recovery.length !== 10) throw new Error(`expected 10 recovery codes, got ${recovery.length}`);
    await shot(page, "03-recovery-codes");
    await page.getByRole("button", { name: "I have saved my codes" }).click();
    await expectUrl(page, "/");
  });

  await check("status page shows API ready", async () => {
    await page.getByText("Ready", { exact: true }).waitFor();
    await shot(page, "04-status");
  });

  await check("owner creates a reviewer account", async () => {
    await page.getByRole("link", { name: "Users" }).click();
    await expectUrl(page, "/users");
    await page.getByLabel("Email").fill(REVIEWER.email);
    await page.getByLabel("Display name").fill("E2E Reviewer");
    await page.getByLabel("Role", { exact: true }).selectOption("REVIEWER");
    await page.getByLabel("Temporary password").fill(REVIEWER.temp);
    await page.getByRole("button", { name: "Create account" }).click();
    await page.getByText(`Created ${REVIEWER.email}`).waitFor();
    await page.getByText("E2E Reviewer").waitFor();
    await shot(page, "05-users");
  });

  await check("activity log lists the privileged actions", async () => {
    await page.getByRole("link", { name: "Activity" }).click();
    await expectUrl(page, "/activity");
    for (const action of ["user.created", "auth.mfa.enabled", "owner.bootstrapped"]) {
      await page.getByRole("cell", { name: action, exact: true }).first().waitFor();
    }
    await shot(page, "06-activity");
  });

  await check("owner signs out", async () => {
    await page.getByRole("button", { name: "Sign out" }).click();
    await expectUrl(page, "/login");
  });

  const rctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const rpage = await rctx.newPage();
  rpage.on("console", (m) => m.type() === "error" && errors.push(m.text()));

  await check("reviewer must change the temporary password", async () => {
    await rpage.goto(`${BASE}/login`);
    await rpage.getByLabel("Email").fill(REVIEWER.email);
    await rpage.getByLabel("Password").fill(REVIEWER.temp);
    await rpage.getByRole("button", { name: "Sign in" }).click();
    await expectUrl(rpage, "/setup/password");
    await rpage.getByLabel("Current password").fill(REVIEWER.temp);
    await rpage.getByLabel("New password", { exact: true }).fill(REVIEWER.next);
    await rpage.getByLabel("Confirm new password").fill(REVIEWER.next);
    await rpage.getByRole("button", { name: "Change password" }).click();
    await expectUrl(rpage, "/");
    await shot(rpage, "07-reviewer-mobile");
  });

  await check("reviewer cannot see or open admin pages", async () => {
    if (await rpage.getByRole("link", { name: "Users" }).count()) throw new Error("Users link visible");
    await rpage.goto(`${BASE}/users`);
    await expectUrl(rpage, "/");
    const api = await rpage.request.get(`${BASE}/api/v1/users`);
    if (api.status() !== 403) throw new Error(`expected 403, got ${api.status()}`);
  });

  await check("owner signs in again with a recovery code", async () => {
    await page.getByLabel("Email").fill(OWNER.email);
    await page.getByLabel("Password").fill(OWNER.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expectUrl(page, "/login/mfa");
    await page.getByRole("button", { name: "Use a recovery code instead" }).click();
    await page.getByLabel("Recovery code").fill(recovery[0]);
    await page.getByRole("button", { name: "Verify" }).click();
    await expectUrl(page, "/");
  });

  await check("account page shows 9 recovery codes left and active sessions", async () => {
    await page.getByRole("link", { name: "Account" }).click();
    await page.getByText("9 of 10 recovery codes left").waitFor();
    await page.getByText("this device").waitFor();
    await shot(page, "08-account");
  });

  await check("expired access cookie is refreshed transparently on navigation", async () => {
    const before = (await ctx.cookies()).find((c) => c.name.endsWith("wf_rt"))?.value;
    await ctx.clearCookies({ name: /wf_at$/ });
    await page.goto(`${BASE}/account`);
    await expectUrl(page, "/account");
    const jar = await ctx.cookies();
    if (!jar.some((c) => c.name.endsWith("wf_at"))) throw new Error("no new access cookie");
    if (jar.find((c) => c.name.endsWith("wf_rt"))?.value === before) throw new Error("refresh token not rotated");
  });

  await check("owner deactivates reviewer; reviewer session ends immediately", async () => {
    await page.getByRole("link", { name: "Users" }).click();
    await page.getByRole("button", { name: "Deactivate" }).click();
    await page.getByText("Deactivated").waitFor();
    const r = await rpage.request.get(`${BASE}/api/v1/auth/me`);
    if (r.status() !== 401) throw new Error(`expected 401, got ${r.status()}`);
  });

  await check("sources start disabled; Google Places explains its blockers", async () => {
    await page.getByRole("link", { name: "Sources" }).click();
    await expectUrl(page, "/sources");
    await page.getByText("Disabled").first().waitFor();
    await page.getByText("GOOGLE_PLACES_API_ENABLED is false.").waitFor();
    const enableWebsite = page
      .locator("section", { hasText: "Business-owned official websites" })
      .getByRole("button", { name: "Enable" });
    if (!(await enableWebsite.isDisabled())) throw new Error("enable allowed without terms review");
    await shot(page, "09-sources");
  });

  await check("owner enables mock places and searches with attribution", async () => {
    const mock = page.locator("section", { hasText: "Mock places (development and tests only)" });
    await mock.getByRole("button", { name: "Enable" }).click();
    await mock.getByLabel("Reason to enable").fill("End-to-end test run");
    await mock.getByRole("button", { name: "Enable source" }).click();
    await mock.getByText("Usable").waitFor();
    await page.getByRole("link", { name: "Places discovery →" }).click();
    await expectUrl(page, "/sources/places");
    await page.getByLabel("Search").fill("dental clinics in Lahore");
    await page.getByLabel("Results (1–20)").fill("3");
    await page.getByRole("button", { name: "Search" }).click();
    await page.getByRole("heading", { name: "3 results" }).waitFor();
    const attribution = (await page.getByTestId("attribution").innerText()).trim();
    if (attribution !== "Mock data - not Google Maps") throw new Error(`attribution: ${attribution}`);
    await page.getByText("Saved: 3 Place IDs (3 new)").waitFor();
    const verify = page.getByRole("button", { name: "Verify website" }).first();
    if (!(await verify.isDisabled())) throw new Error("verify enabled before website source");
    await shot(page, "10-places-search");
  });

  await check("owner records a terms review and enables website verification", async () => {
    await page.getByRole("link", { name: "← Sources" }).click();
    const site = page.locator("section", { hasText: "Business-owned official websites" });
    await site.getByRole("button", { name: "Record terms review" }).click();
    await site.getByLabel("Terms URL (https)").fill("https://example.test/website-verification-policy");
    await site.getByLabel("Version or date reviewed").fill("2026-11-26");
    await site
      .getByLabel("What you checked and decided")
      .fill("Public pages only, robots.txt respected, no forms or logins. E2E fixture review.");
    await site.getByRole("button", { name: "Save review" }).click();
    await site.getByText("2026-11-26 ·").waitFor();
    await site.getByRole("button", { name: "Enable" }).click();
    await site.getByLabel("Reason to enable").fill("End-to-end test run");
    await site.getByRole("button", { name: "Enable source" }).click();
    await site.getByText("Usable").waitFor();
  });

  await check("verifying an unreachable fixture site holds it and stores nothing else", async () => {
    await page.getByRole("link", { name: "Places discovery →" }).click();
    await page.getByLabel("Search").fill("dental clinics in Lahore");
    await page.getByLabel("Results (1–20)").fill("3");
    await page.getByRole("button", { name: "Search" }).click();
    await page.getByText("Saved: 3 Place IDs (0 new)").waitFor();
    await page.getByRole("button", { name: "Verify website" }).first().click();
    await page.getByText("On hold — needs review").waitFor({ timeout: 40_000 });
    await shot(page, "11-verification-hold");
    await page.reload();
    await page.getByRole("cell", { name: "mock_places" }).first().waitFor();
    await page.getByText("HOLD").first().waitFor();
    await page.getByText("The website could not be reached.").first().waitFor();
  });

  await check("activity log records source governance", async () => {
    await page.getByRole("link", { name: "Activity" }).click();
    for (const action of ["source.enabled", "source.terms_reviewed", "places.search", "website.verification"]) {
      await page.getByRole("cell", { name: action, exact: true }).first().waitFor();
    }
  });

  await check("owner resumes the global pause in Settings", async () => {
    await page.getByRole("link", { name: "Settings" }).click();
    await expectUrl(page, "/settings");
    const g = page.locator("section", { hasText: "Global pause" });
    await g.getByText("PAUSED", { exact: true }).waitFor();
    await g.getByLabel("Reason").fill("E2E run");
    await g.getByRole("button", { name: "Resume" }).click();
    await g.getByText("RUNNING", { exact: true }).waitFor();
  });

  await check("owner creates, activates and runs a mock campaign", async () => {
    await page.getByRole("link", { name: "Campaigns" }).click();
    await expectUrl(page, "/campaigns");
    await page.getByLabel("Campaign name").fill("E2E dental clinics");
    await page.getByLabel("Target countries (ISO codes, comma-separated)").fill("PK");
    await page.getByLabel("Discovery searches (one per line)").fill("dental clinics in Lahore");
    await page.getByLabel("Dental clinics").check();
    await page.getByLabel("Candidate cap").fill("3");
    await page.getByRole("button", { name: "Create campaign" }).click();
    await page.getByRole("heading", { name: "E2E dental clinics" }).waitFor();
    await page.getByRole("button", { name: "Activate" }).click();
    await page.getByText("active", { exact: true }).waitFor();
    await page.getByRole("button", { name: "Run discovery now" }).click();
    await shot(page, "12-campaign");
  });

  await check("worker processes discovery jobs; unverifiable sites are held, not stored", async () => {
    const deadline = Date.now() + 60_000;
    for (;;) {
      await page.reload();
      const text = await page.locator("dl").first().innerText();
      if (/Jobs succeeded\s*4/.test(text)) break;
      if (Date.now() > deadline) throw new Error(`jobs did not finish: ${text}`);
      await page.waitForTimeout(2000);
    }
    await page.getByText("Candidate Place IDs").waitFor();
    await page.getByText("No prospects yet.").waitFor();
    await page.getByRole("link", { name: "Jobs", exact: true }).click();
    await page.getByRole("cell", { name: "discovery.search" }).first().waitFor();
    await shot(page, "13-jobs");
  });

  await check("no browser console errors", async () => {
    const real = errors.filter((e) => !/401|403|409|Failed to load resource/.test(e));
    if (real.length) throw new Error(real.join(" | "));
  });
} finally {
  await browser.close();
}
console.log(`All ${step} end-to-end checks passed.`);
