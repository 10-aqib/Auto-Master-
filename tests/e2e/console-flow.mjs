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

  await check("owner generates and approves a mock AI brief for an audited fixture prospect", async () => {
    // Offline fixture sites never pass a real audit here, so seed one audited test prospect directly.
    const sql = `
      WITH p AS (
        INSERT INTO prospects (id, business_name, verified_domain, website_url, industry, state)
        VALUES (gen_random_uuid(), 'E2E Fixture Bakery', 'bakery.example.test', 'https://bakery.example.test/',
                'bakery', 'AUDITED') RETURNING id),
      s AS (
        INSERT INTO prospect_sources (id, prospect_id, source_type, source_name, source_url, fact_field, safe_value,
                                      retrieved_at, confidence, verification_method, is_independent)
        SELECT gen_random_uuid(), id, 'OFFICIAL_WEBSITE', 'Official website', 'https://bakery.example.test/',
               'business_name', 'E2E Fixture Bakery', now(), 0.9, 'e2e_fixture', true FROM p),
      a AS (
        INSERT INTO website_audits (id, prospect_id, url, status, audit_version, started_at, finished_at, scores)
        SELECT gen_random_uuid(), id, 'https://bakery.example.test/', 'SUCCEEDED', 'audit-1', now(), now(),
               '{"overall": 61}'::jsonb FROM p RETURNING id, prospect_id),
      f AS (
        INSERT INTO audit_findings (id, audit_id, category, severity, code, description, viewport, observed_at)
        SELECT gen_random_uuid(), id, 'mobile_usability', 'HIGH', 'MOBILE_HORIZONTAL_OVERFLOW',
               'The home page scrolls sideways on a 390px phone screen. Content is cut off.', 'mobile', now() FROM a)
      SELECT prospect_id FROM a;`;
    const out = execFileSync(
      "docker",
      ["compose", "exec", "-T", "postgres", "psql", "-U", "webforge", "-d", "webforge", "-tA", "-v", "ON_ERROR_STOP=1"],
      { input: sql },
    ).toString();
    const prospectId = out.match(/[0-9a-f-]{36}/)?.[0];
    if (!prospectId) throw new Error(`seed failed: ${out}`);
    await page.goto(`${BASE}/prospects/${prospectId}`);
    await page.getByRole("heading", { name: "E2E Fixture Bakery" }).waitFor();
    await page.getByRole("button", { name: "Generate brief" }).click();
    const deadline = Date.now() + 60_000;
    for (;;) {
      await page.reload();
      const link = page.getByRole("link", { name: "Version 1" });
      if ((await link.count()) && (await page.getByText("mock-brief-model-1").count())) break;
      if (Date.now() > deadline) throw new Error("brief job did not finish");
      await page.waitForTimeout(2000);
    }
    await page.getByRole("link", { name: "Version 1" }).click();
    await page.getByRole("heading", { name: "Design brief" }).waitFor();
    await page.getByText("Six screens").waitFor();
    await page.getByText("Independent redesign concept plan.").waitFor();
    await shot(page, "14-design-brief");
    await page.getByLabel("Review notes").fill("E2E approval");
    await page.getByRole("button", { name: "Approve brief" }).click();
    await page.getByText("approved", { exact: true }).waitFor();
  });

  await check("owner renders a six-screen concept and previews it in a sandboxed frame", async () => {
    await page.getByRole("button", { name: "Render concept" }).click();
    const deadline = Date.now() + 60_000;
    for (;;) {
      await page.reload();
      if (await page.getByText("Concept v1").count()) break;
      if (Date.now() > deadline) throw new Error("render job did not finish");
      await page.waitForTimeout(2000);
    }
    const tabs = page.getByRole("tablist", { name: "Concept pages" }).getByRole("tab");
    if ((await tabs.count()) !== 6) throw new Error(`expected 6 page tabs, got ${await tabs.count()}`);
    const frameEl = page.locator("iframe[title^='Concept preview']");
    if ((await frameEl.getAttribute("sandbox")) !== "allow-same-origin") throw new Error("preview iframe is not sandboxed");
    const frame = page.frameLocator("iframe[title^='Concept preview']");
    await frame.getByText("Independent redesign concept — not the official website").first().waitFor();
    // In-frame navigation works; the demo form cannot submit anything.
    await frame.getByRole("link", { name: "Make an Inquiry" }).first().click();
    await frame.getByText("Demo only. This form does not send, save or collect anything.").waitFor();
    await frame.getByLabel("Your name").fill("Test Person");
    const conceptFrame = () => page.frames().find((f) => f.url().includes("/api/concepts/"));
    const before = conceptFrame()?.url();
    await frame.getByRole("button", { name: "Send enquiry" }).click();
    await frame.getByLabel("Your name").press("Enter");
    await page.waitForTimeout(500);
    await frame.getByLabel("Your name").waitFor();
    const after = conceptFrame()?.url();
    if (!before?.endsWith("/inquiry") || before !== after) throw new Error(`demo form navigated: ${before} -> ${after}`);
    await page.getByRole("button", { name: "Mobile", exact: true }).click();
    await shot(page, "15-concept-mobile");
    // Direct load at phone width: no horizontal overflow.
    const phone = await ctx.newPage();
    await phone.setViewportSize({ width: 390, height: 844 });
    const href = await frameEl.getAttribute("src");
    const res = await phone.goto(`${BASE}${href}`);
    const csp = res?.headers()["content-security-policy"] ?? "";
    if (!csp.startsWith("sandbox allow-same-origin;") || !csp.includes("form-action 'none'") || /allow-scripts/.test(csp)) throw new Error(`csp: ${csp}`);
    const sw = await phone.evaluate(() => document.documentElement.scrollWidth);
    if (sw > 390) throw new Error(`horizontal overflow at 390px: ${sw}`);
    await phone.close();
  });

  await check("offline validation passes at three widths with 18 screenshots, then the owner approves", async () => {
    const deadline = Date.now() + 180_000;
    for (;;) {
      await page.reload();
      if (await page.getByText("ready", { exact: true }).count()) break;
      if (await page.getByText("needs revision", { exact: true }).count()) {
        await shot(page, "16-validation-failed");
        throw new Error("validation needs revision");
      }
      if (Date.now() > deadline) throw new Error("validation did not finish");
      await page.waitForTimeout(3000);
    }
    const summary = await page.getByText(/checks passed/).first().innerText();
    if (!/0 critical/.test(summary)) throw new Error(`summary: ${summary}`);
    await page.getByText("Screenshots (18)").click();
    const img = page.getByRole("img", { name: "inquiry page at mobile width" });
    await img.waitFor();
    await img.scrollIntoViewIfNeeded();
    await img.evaluate((el) => (el.complete ? null : new Promise((r) => el.addEventListener("load", r, { once: true }))));
    const natural = await img.evaluate((el) => el.naturalWidth);
    if (natural !== 780) throw new Error(`mobile screenshot should be 390px at 2x, got ${natural}`);
    await shot(page, "16-validation-ready");
    await page.getByRole("button", { name: "Approve concept" }).click();
    await page.getByText("active", { exact: true }).waitFor();
    await shot(page, "17-concept-approved");
  });

  await check("owner generates a proposal PDF and opens a token preview from a separate origin", async () => {
    await page.getByRole("button", { name: "Generate proposal" }).click();
    const deadline = Date.now() + 180_000;
    for (;;) {
      await page.reload();
      if (await page.getByRole("link", { name: "Download PDF" }).count()) break;
      if (await page.getByText(/Checks failed:/).count()) throw new Error("proposal checks failed");
      if (Date.now() > deadline) throw new Error("proposal did not finish");
      await page.waitForTimeout(3000);
    }
    const pdfHref = await page.getByRole("link", { name: "Download PDF" }).getAttribute("href");
    const pdf = await page.request.get(`${BASE}${pdfHref}`);
    const bytes = await pdf.body();
    if (!pdf.ok() || bytes.subarray(0, 5).toString() !== "%PDF-") throw new Error("PDF download failed");
    const pages = Math.max(0, ...[...bytes.toString("latin1").matchAll(/\/Count (\d+)/g)].map((m) => Number(m[1])));
    if (pages < 10) throw new Error(`PDF has ${pages} pages`);
    await page.getByRole("button", { name: "Create preview link" }).click();
    const url = (await page.getByTestId("preview-url").innerText()).trim();
    if (!/^http:\/\/localhost:4000\/p\/[A-Za-z0-9_-]{43,}\/$/.test(url)) throw new Error(`preview url: ${url}`);
    await shot(page, "18-proposal");
    // A recipient: fresh browser context, no dashboard cookies, different origin.
    const visitor = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const v = await visitor.newPage();
    const res = await v.goto(url);
    if (!v.url().endsWith("/home") || res?.status() !== 200) throw new Error(`preview open: ${v.url()} ${res?.status()}`);
    const headers = res.headers();
    if (!headers["content-security-policy"]?.startsWith("sandbox;") || headers["x-frame-options"] !== "DENY")
      throw new Error("preview security headers missing");
    await v.getByText("Independent redesign concept — not the official website").first().waitFor();
    await v.getByRole("link", { name: "Make an Inquiry" }).first().click();
    await v.getByText("Demo only. This form does not send, save or collect anything.").waitFor();
    await shot(v, "19-preview-mobile");
    const pdfRes = await v.request.get(`${url}proposal.pdf`);
    if (pdfRes.status() !== 200 || pdfRes.headers()["content-type"] !== "application/pdf") throw new Error("preview pdf");
    if ((await v.request.get(url.replace(/\/p\/[^/]+\//, "/p/" + "A".repeat(43) + "/") + "home")).status() !== 404)
      throw new Error("wrong token not refused");
    // Immediate revocation.
    await page.getByRole("button", { name: "Revoke" }).click();
    await page.getByText("preview revoked").waitFor();
    if ((await v.request.get(`${url}home`)).status() !== 404) throw new Error("revoked preview still served");
    await visitor.close();
  });

  await check("compliance gate: reviewed policy, contact, 17 checks, owner approval, mock send, reply and unsubscribe", async () => {
    page.on("dialog", (d) => d.accept());
    const prospectUrl = `${BASE}${await page.getByRole("link", { name: "← Prospect" }).getAttribute("href")}`;
    // 1. A policy recorded as reviewed (test fixture values only).
    await page.getByRole("link", { name: "Compliance", exact: true }).click();
    await page.getByText("Add a policy draft").click();
    await page.getByLabel("Country (ISO code)").first().fill("US");
    await page.getByLabel("Version").fill("e2e-1");
    await page.getByLabel("Official source URLs (one per line)").fill("https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business");
    await page.getByLabel("Rules (JSON, as advised by counsel)").fill(JSON.stringify({
      permitted: true, legal_bases: ["legitimate_interest"], consent_required: false,
      disclosures: ["sender_identity", "physical_address", "unsubscribe", "concept_notice"], unsubscribe: "link + one-click",
      retention_days: 365, next_review: "2099-01-01", personal_data_reviewed: true,
    }));
    await page.getByRole("button", { name: "Save draft" }).click();
    await page.getByText("Record legal review and activate").click();
    await page.getByLabel("Reviewer name").fill("E2E Fixture Reviewer");
    await page.getByLabel("Reviewer qualification").fill("Test fixture only");
    await page.getByLabel("Reviewed on").fill("2026-11-01");
    await page.getByLabel("Effective from").fill("2026-11-01");
    await page.getByRole("button", { name: "Activate policy" }).click();
    await page.getByText("E2E Fixture Reviewer (Test fixture only)").waitFor();
    await shot(page, "20-compliance");
    // 2. Resume the email pause (seeded paused).
    await page.getByRole("link", { name: "Settings" }).click();
    const e = page.locator("section").filter({ has: page.getByRole("heading", { name: "Email pause", exact: true }) }).last();
    await e.getByLabel("Reason").fill("E2E mock send");
    await e.getByRole("button", { name: "Resume" }).click();
    await e.getByText("RUNNING", { exact: true }).waitFor();
    // 3. Contact from the official site, draft, checks.
    await page.goto(prospectUrl);
    await page.getByText("Add a contact").click();
    await page.getByLabel("Email address").fill("hello@bakery.example.test");
    await page.getByLabel("Country (ISO code)").fill("US");
    await page.getByLabel("Page where it is published (https)").fill("https://bakery.example.test/contact");
    await page.getByRole("button", { name: "Save contact" }).click();
    await page.getByText("h•••@bakery.example.test", { exact: true }).waitFor();
    await page.getByText("Draft the initial message").click();
    await page.getByLabel("Legal basis (as reviewed by counsel)").selectOption("legitimate_interest");
    await page.getByLabel("Evidence for that basis").fill("E2E fixture: counsel memo reference for corporate role address.");
    await page.getByRole("button", { name: "Draft and check" }).click();
    await page.getByText("compliance eligible").waitFor();
    await page.getByText("Pre-send checks (17/17 pass)").waitFor();
    await shot(page, "21-outreach-eligible");
    // 4. Owner approval -> worker sends through the mock provider.
    await page.getByRole("button", { name: "Approve and send" }).click();
    const deadline = Date.now() + 90_000;
    for (;;) {
      await page.reload();
      if (await page.getByText("accepted", { exact: true }).count()) break;
      if (Date.now() > deadline) throw new Error("mock send did not complete");
      await page.waitForTimeout(2000);
    }
    await page.getByText(/^Message: /).click();
    const body = await page.locator("pre").first().innerText();
    if (!body.includes("independent redesign concept") || !/\/p\/[A-Za-z0-9_-]{43}\//.test(body)) throw new Error("sent body missing preview");
    const unsub = body.match(/https?:\/\/[^\s]+\/u\/[A-Za-z0-9_-]+/)?.[0];
    if (!unsub) throw new Error("no unsubscribe link");
    // 5. Simulated reply lands in Replies, classified.
    const [simulated] = await Promise.all([
      page.waitForResponse((res) => res.url().includes("/simulate")),
      page.getByRole("button", { name: "Simulate reply" }).click(),
    ]);
    if (simulated.status() !== 200) throw new Error(`simulate reply: ${simulated.status()}`);
    await page.getByRole("link", { name: "Replies" }).click();
    await page.getByText("interested", { exact: true }).first().waitFor();
    await shot(page, "22-replies");
    // 6. Recipient unsubscribes (no login, separate context): GET shows a button, POST suppresses.
    const recipient = await browser.newContext();
    const r = await recipient.newPage();
    await r.goto(unsub.replace("localhost", "127.0.0.1"));
    await r.getByRole("button", { name: "Unsubscribe" }).click();
    await r.getByRole("heading", { name: "You are unsubscribed" }).waitFor();
    await recipient.close();
    await page.goto(prospectUrl);
    await page.getByText("suppressed", { exact: true }).first().waitFor();
    await shot(page, "23-unsubscribed");
  });

  await check("no browser console errors", async () => {
    const real = errors.filter((e) => !/401|403|409|Failed to load resource/.test(e));
    if (real.length) throw new Error(real.join(" | "));
  });
} finally {
  await browser.close();
}
console.log(`All ${step} end-to-end checks passed.`);
