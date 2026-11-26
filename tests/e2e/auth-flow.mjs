// End-to-end browser test of the Phase 01 auth flow against a running local stack.
// Usage: node tests/e2e/auth-flow.mjs   (requires `make dev`, an EMPTY users table, and Playwright)
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

  await check("no browser console errors", async () => {
    const real = errors.filter((e) => !/401|403|Failed to load resource/.test(e));
    if (real.length) throw new Error(real.join(" | "));
  });
} finally {
  await browser.close();
}
console.log(`All ${step} end-to-end checks passed.`);
