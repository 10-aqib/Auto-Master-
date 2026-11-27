import Link from "next/link";
import { Suspense } from "react";
import { connection } from "next/server";

import { Badge } from "@/components/badge";
import { StatusPanel, StatusPanelSkeleton } from "@/components/status-panel";
import { Alert, Card } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import { fetchApiHealth } from "@/lib/health";
import { QUEUE_LABEL, type Overview, type ReviewQueues } from "@/lib/overview";
import { getServerConfig } from "@/lib/server-config";

export const metadata = { title: "Overview · WEBFORGE AI" };

async function LiveApiStatus() {
  await connection(); // always check at request time, never at build time
  const health = await fetchApiHealth(getServerConfig().apiInternalUrl);
  return <StatusPanel health={health} />;
}

const STAGE_LABEL: Record<string, string> = {
  DISCOVERED: "Discovered",
  SOURCE_VERIFYING: "Verifying source",
  VERIFIED: "Verified",
  DEDUPLICATED: "Deduplicated",
  QUALIFYING: "Qualifying",
  QUALIFIED: "Qualified",
  AUDITING: "Auditing",
  AUDITED: "Audited",
  GENERATING_DESIGN: "Generating design",
  VALIDATING: "Validating",
  PROPOSAL_READY: "Proposal ready",
  COMPLIANCE_CHECK: "Compliance check",
  SCHEDULED: "Scheduled",
  SENT: "Sent",
  DELIVERED: "Delivered",
  REPLIED: "Replied",
  INTERESTED: "Interested",
  CLIENT: "Client",
};

export default async function OverviewPage({ searchParams }: PageProps<"/">) {
  await requireActiveSession();
  const sp = await searchParams;
  const country = typeof sp.country === "string" && /^[A-Z]{2}$/.test(sp.country) ? sp.country : "";
  const [data, queues] = await Promise.all([
    apiServer<Overview>(`/overview${country ? `?country=${country}` : ""}`),
    apiServer<ReviewQueues>("/review-queues"),
  ]);
  if (!data.ok) return <Alert>{data.error.message}</Alert>;
  const o = data.data;
  const top = Math.max(1, ...o.funnel.map((f) => f.reached));
  const warnings = o.budgets.filter((b) => b.status !== "ok");

  return (
    <div className="grid gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
          <p className="mt-1 text-sm text-muted">
            Pipeline, holds, budgets and work waiting for you. {o.tracking_note}
          </p>
        </div>
        <form className="flex items-end gap-2 text-sm" action="/">
          <label className="grid gap-1 font-medium">
            Country
            <input
              name="country"
              defaultValue={country}
              maxLength={2}
              placeholder="All"
              className="min-h-10 w-24 rounded-lg border border-line bg-background px-3 uppercase"
            />
          </label>
          <button type="submit" className="min-h-10 rounded-lg border border-line px-3 hover:bg-background">
            Filter
          </button>
        </form>
      </header>

      {warnings.length > 0 && (
        <Alert tone={warnings.some((w) => w.status === "stopped") ? "error" : "info"}>
          <span className="font-medium">Budget limits:</span>{" "}
          {warnings
            .map(
              (w) =>
                `${w.label} ${w.status === "stopped" ? "stopped" : `at ${Math.round((w.ratio ?? 0) * 100)}%`}`,
            )
            .join(" · ")}
        </Alert>
      )}

      <section aria-label="Outcomes" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {(
          [
            ["Sent", o.outcomes.sent],
            ["Delivered", o.outcomes.delivered],
            ["Replied", o.outcomes.replied],
            ["Interested", o.outcomes.interested],
            ["Bounced", o.outcomes.bounced],
            ["Complaints", o.outcomes.complained],
            ["Opted out", o.outcomes.opted_out],
            ["Clients", o.outcomes.converted],
          ] as const
        ).map(([label, value]) => (
          <div key={label} className="rounded-xl border border-line bg-surface p-4">
            <p className="text-xs text-muted">{label}</p>
            <p className="text-2xl font-semibold tabular-nums">{value}</p>
          </div>
        ))}
      </section>

      {queues.ok && (
        <Card
          title="Waiting for you"
          actions={
            <Link href="/review" className="text-sm text-accent hover:underline">
              Open review queues
            </Link>
          }
        >
          <ul className="grid gap-1 text-sm sm:grid-cols-2">
            {Object.entries(queues.data.counts).map(([k, n]) => (
              <li key={k} className="flex items-center justify-between gap-2">
                <span>{QUEUE_LABEL[k] ?? k}</span>
                <Badge value={n ? "HOLD" : "SUCCEEDED"} label={String(n)} />
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Pipeline (prospects that reached each stage)">
        <ol className="grid gap-1.5 text-sm">
          {o.funnel.map((f) => (
            <li
              key={f.stage}
              className="grid grid-cols-[9rem_1fr_3rem] items-center gap-2 sm:grid-cols-[11rem_1fr_4rem]"
            >
              <span className="truncate">{STAGE_LABEL[f.stage] ?? f.stage}</span>
              <span className="h-3 rounded bg-background" aria-hidden="true">
                <span
                  className="block h-3 rounded bg-accent/70"
                  style={{ width: `${(f.reached / top) * 100}%` }}
                />
              </span>
              <span className="text-right tabular-nums">{f.reached}</span>
            </li>
          ))}
        </ol>
        <p className="mt-3 text-xs text-muted">
          On hold or stopped:{" "}
          {Object.entries(o.holds_and_exits)
            .filter(([, n]) => n > 0)
            .map(([k, n]) => `${k.toLowerCase().replaceAll("_", " ")} ${n}`)
            .join(" · ") || "none"}
        </p>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Why leads are held (last 30 days)">
          {o.hold_reasons.length ? (
            <ul className="grid gap-1 text-sm">
              {o.hold_reasons.map((r) => (
                <li key={r.reason} className="flex justify-between gap-2">
                  <span>{r.reason.replaceAll("_", " ")}</span>
                  <span className="tabular-nums">{r.count}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">No compliance holds recorded.</p>
          )}
        </Card>
        <Card title="Budgets today">
          <ul className="grid gap-2 text-sm">
            {o.budgets.map((b) => (
              <li key={b.key} className="grid gap-1">
                <div className="flex justify-between gap-2">
                  <span>{b.label}</span>
                  <Badge
                    value={b.status === "ok" ? "SUCCEEDED" : b.status === "warning" ? "HOLD" : "FAILED"}
                    label={b.status}
                  />
                </div>
                <span className="text-xs text-muted">
                  {b.used} / {b.limit} {b.unit}
                  {b.note ? ` — ${b.note}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="By campaign">
          {o.by_campaign.length ? (
            <ul className="grid gap-1 text-sm">
              {o.by_campaign.map((c) => (
                <li key={c.campaign_id} className="flex justify-between gap-2">
                  <Link href={`/campaigns/${c.campaign_id}`} className="text-accent hover:underline">
                    {c.name}
                  </Link>
                  <span className="text-muted">
                    {c.status.toLowerCase()} · {c.prospects} prospects
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">No campaigns yet.</p>
          )}
        </Card>
        <Card title="By country · spend this month">
          <ul className="grid gap-1 text-sm">
            {o.by_country.map((c) => (
              <li key={c.country} className="flex justify-between gap-2">
                <Link
                  href={c.country === "unknown" ? "/" : `/?country=${c.country}`}
                  className="text-accent hover:underline"
                >
                  {c.country}
                </Link>
                <span className="tabular-nums">{c.prospects}</span>
              </li>
            ))}
          </ul>
          <ul className="mt-3 grid gap-1 border-t border-line pt-3 text-sm">
            {o.spend_this_month.length ? (
              o.spend_this_month.map((s) => (
                <li key={s.provider} className="flex justify-between gap-2">
                  <span>{s.provider}</span>
                  <span className="tabular-nums">
                    {s.calls} calls · ${(s.cost_cents / 100).toFixed(2)}
                  </span>
                </li>
              ))
            ) : (
              <li className="text-muted">No paid usage this month.</li>
            )}
          </ul>
        </Card>
      </div>

      <Suspense fallback={<StatusPanelSkeleton />}>
        <LiveApiStatus />
      </Suspense>
    </div>
  );
}
