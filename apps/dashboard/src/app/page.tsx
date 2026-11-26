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
  "Google Places discovery is disabled until the policy-safe connector exists.",
  "Global and email pause switches default to ON (fail closed).",
];

export default function Home() {
  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-10 sm:px-6 sm:py-16">
      <header>
        <p className="text-xs font-semibold uppercase tracking-widest text-accent">WEBFORGE AI</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">System status</h1>
        <p className="mt-2 text-sm text-muted">
          Foundation build (Phase 00). Business modules such as campaigns, audits and outreach are not
          implemented yet, so they are intentionally absent from this console.
        </p>
      </header>

      <div className="mt-8 grid gap-6">
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
    </main>
  );
}
