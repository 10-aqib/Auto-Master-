import { Suspense } from "react";
import { connection } from "next/server";

import { StatusPanel, StatusPanelSkeleton } from "@/components/status-panel";
import { fetchApiHealth } from "@/lib/health";
import { getServerConfig } from "@/lib/server-config";

async function LiveApiStatus() {
  await connection(); // always check at request time, never at build time
  const health = await fetchApiHealth(getServerConfig().apiInternalUrl);
  return <StatusPanel health={health} />;
}

const SAFETY_DEFAULTS = [
  "External email sending is disabled and cannot be enabled in this build.",
  "Every data source starts disabled and needs an owner terms review before use.",
  "Only Google Place IDs are stored; other Maps content is shown once with attribution.",
  "Global and email pause switches default to ON (fail closed).",
];

export default function Home() {
  return (
    <div className="grid gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">System status</h1>
        <p className="mt-2 text-sm text-muted">
          Accounts, sign-in and the activity log are live. Campaigns, audits and outreach arrive in later
          phases, so they are not shown yet.
        </p>
      </header>
      <Suspense fallback={<StatusPanelSkeleton />}>
        <LiveApiStatus />
      </Suspense>
      <section aria-labelledby="safety" className="rounded-xl border border-line bg-surface p-5 shadow-sm">
        <h2 id="safety" className="text-base font-semibold">
          Safety defaults
        </h2>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm text-muted">
          {SAFETY_DEFAULTS.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
