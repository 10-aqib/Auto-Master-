import Link from "next/link";

import { ActionButton } from "@/components/action-button";
import { Badge } from "@/components/badge";
import { CampaignForm } from "@/components/campaign-form";
import { ProspectTable } from "@/components/prospect-table";
import { Alert, Card } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import type { CampaignDetail, Control, ProspectPage } from "@/lib/discovery";
import { formatMinor } from "@/lib/sources";

export const metadata = { title: "Campaign · WEBFORGE AI" };

export default async function CampaignPage({ params }: PageProps<"/campaigns/[id]">) {
  const { id } = await params;
  const { user } = await requireActiveSession();
  const [detail, prospects, industries, controls] = await Promise.all([
    apiServer<CampaignDetail>(`/campaigns/${id}`),
    apiServer<ProspectPage>(`/prospects?campaign_id=${id}&limit=100`),
    apiServer<Record<string, string>>("/industries"),
    apiServer<Control[]>("/controls"),
  ]);
  if (!detail.ok) return <Alert>{detail.error.message}</Alert>;
  const { campaign: c, readiness, stats } = detail.data;
  const canEdit = user.role === "OWNER" || user.role === "ADMIN";
  const paused = controls.ok ? Boolean(controls.data.find((x) => x.key === "global_pause")?.effective) : true;
  const notReady = readiness.filter((r) => !r.ok);

  return (
    <div className="grid gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm">
            <Link href="/campaigns" className="text-accent hover:underline">
              ← Campaigns
            </Link>
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">{c.name}</h1>
          <p className="mt-1 text-sm text-muted">
            {c.target_countries.join(", ")} · source {c.filters.source_key} · cap {c.candidate_cap} · budget{" "}
            {formatMinor(c.daily_budget_minor, "USD")}/day · email sending {c.sending_mode.toLowerCase()}
          </p>
        </div>
        <Badge value={c.status} />
      </header>

      {canEdit && (
        <div className="flex flex-wrap gap-3">
          {c.status === "DRAFT" && (
            <ActionButton
              path={`/campaigns/${id}/activate`}
              body={{ reason: "activated" }}
              label="Activate"
              variant="primary"
              disabledReason={notReady.length ? "Fix the readiness checks first." : undefined}
            />
          )}
          {c.status === "ACTIVE" && (
            <>
              <ActionButton
                path={`/campaigns/${id}/discover`}
                label="Run discovery now"
                variant="primary"
                disabledReason={paused ? "The system is paused (Settings)." : undefined}
              />
              <ActionButton
                path={`/campaigns/${id}/pause`}
                body={{ reason: "paused from dashboard" }}
                label="Pause"
              />
            </>
          )}
          {c.status === "PAUSED" && (
            <ActionButton
              path={`/campaigns/${id}/resume`}
              body={{ reason: "resumed" }}
              label="Resume"
              variant="primary"
              disabledReason={notReady.length ? "Fix the readiness checks first." : undefined}
            />
          )}
          {(c.status === "ACTIVE" || c.status === "PAUSED") && (
            <ActionButton
              path={`/campaigns/${id}/complete`}
              body={{ reason: "completed" }}
              label="Mark complete"
              confirmText="Complete this campaign? Queued discovery jobs will be cancelled."
            />
          )}
          {(c.status === "DRAFT" || c.status === "PAUSED" || c.status === "COMPLETED") && (
            <ActionButton
              path={`/campaigns/${id}/archive`}
              body={{ reason: "archived" }}
              label="Archive"
              variant="danger"
              confirmText="Archive this campaign?"
            />
          )}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Readiness">
          <ul className="grid gap-2 text-sm">
            {readiness.map((r) => (
              <li key={r.code} className="flex items-start gap-2">
                <span aria-hidden="true" className={r.ok ? "text-emerald-600" : "text-rose-600"}>
                  {r.ok ? "✓" : "✗"}
                </span>
                <span>
                  <span className="sr-only">{r.ok ? "Passed: " : "Failing: "}</span>
                  {r.message}
                </span>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Progress">
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted">Candidate Place IDs</dt>
            <dd className="tabular-nums">{stats.candidates}</dd>
            <dt className="text-muted">Verified prospects</dt>
            <dd className="tabular-nums">{stats.prospects}</dd>
            {Object.entries(stats.jobs).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-muted">Jobs {k.toLowerCase()}</dt>
                <dd className="tabular-nums">{v}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-xs">
            <Link href="/jobs" className="text-accent hover:underline">
              View all jobs →
            </Link>
          </p>
        </Card>
      </div>

      <section className="grid gap-3">
        <h2 className="text-lg font-semibold">Prospects</h2>
        {prospects.ok ? (
          <ProspectTable items={prospects.data.items} />
        ) : (
          <Alert>{prospects.error.message}</Alert>
        )}
      </section>

      {canEdit && (c.status === "DRAFT" || c.status === "PAUSED") && industries.ok && (
        <Card title="Edit campaign">
          <CampaignForm industries={industries.data} existing={c} />
        </Card>
      )}
    </div>
  );
}
