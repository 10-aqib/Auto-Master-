import type { ApiHealth } from "@/lib/health";

const SUMMARY: Record<ApiHealth["kind"], { label: string; tone: string }> = {
  ready: {
    label: "Ready",
    tone: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 ring-emerald-500/30",
  },
  not_ready: {
    label: "Degraded",
    tone: "bg-amber-500/15 text-amber-800 dark:text-amber-300 ring-amber-500/30",
  },
  unreachable: {
    label: "Unreachable",
    tone: "bg-rose-500/15 text-rose-700 dark:text-rose-300 ring-rose-500/30",
  },
};

function Badge({ label, tone }: { label: string; tone: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${tone}`}
    >
      {label}
    </span>
  );
}

export function StatusPanel({ health }: { health: ApiHealth }) {
  const summary = SUMMARY[health.kind];
  return (
    <section aria-labelledby="api-status" className="rounded-xl border border-line bg-surface p-5 shadow-sm">
      <div className="flex items-center justify-between gap-4">
        <h2 id="api-status" className="text-base font-semibold">
          API service
        </h2>
        <Badge {...summary} />
      </div>

      {health.kind === "unreachable" ? (
        <p className="mt-3 text-sm text-muted">The dashboard could not reach the API: {health.reason}.</p>
      ) : (
        <table className="mt-4 w-full text-sm">
          <caption className="sr-only">Dependency readiness checks</caption>
          <thead>
            <tr className="text-left text-muted">
              <th scope="col" className="pb-2 font-medium">
                Dependency
              </th>
              <th scope="col" className="pb-2 font-medium">
                Status
              </th>
              <th scope="col" className="pb-2 text-right font-medium">
                Latency
              </th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(health.checks).map(([name, check]) => (
              <tr key={name} className="border-t border-line">
                <th scope="row" className="py-2 text-left font-medium capitalize">
                  {name}
                </th>
                <td className="py-2">
                  {check.status === "ok" ? (
                    <Badge label="OK" tone={SUMMARY.ready.tone} />
                  ) : (
                    <Badge
                      label={`Failed${check.error ? ` (${check.error})` : ""}`}
                      tone={SUMMARY.unreachable.tone}
                    />
                  )}
                </td>
                <td className="py-2 text-right tabular-nums text-muted">
                  {check.latency_ms === null ? "—" : `${check.latency_ms.toFixed(1)} ms`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export function StatusPanelSkeleton() {
  return (
    <section aria-busy="true" className="rounded-xl border border-line bg-surface p-5 shadow-sm">
      <h2 className="text-base font-semibold">API service</h2>
      <p className="mt-3 text-sm text-muted">Checking readiness…</p>
    </section>
  );
}
