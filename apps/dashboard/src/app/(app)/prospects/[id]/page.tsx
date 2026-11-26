import Link from "next/link";

import { ActionButton } from "@/components/action-button";
import { Badge } from "@/components/badge";
import { ProspectReview } from "@/components/prospect-review";
import { Alert, Card, formatDate } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import { COMPONENT_LABEL, type Audit, type ProspectDetail } from "@/lib/discovery";
import { type DesignProject } from "@/lib/designs";
import { reasonText } from "@/lib/sources";

export const metadata = { title: "Prospect · WEBFORGE AI" };

export default async function ProspectPage({ params }: PageProps<"/prospects/[id]">) {
  const { id } = await params;
  const { user } = await requireActiveSession();
  const [detail, audits, designs] = await Promise.all([
    apiServer<ProspectDetail>(`/prospects/${id}`),
    apiServer<Audit[]>(`/audits?prospect_id=${id}`),
    apiServer<DesignProject[]>(`/designs?prospect_id=${id}`),
  ]);
  if (!detail.ok) return <Alert>{detail.error.message}</Alert>;
  const { prospect: p, facts, verifications, place_ids, campaigns, qualifications, merges } = detail.data;
  const latest = qualifications[0];
  const canAdmin = user.role === "OWNER" || user.role === "ADMIN";

  return (
    <div className="grid gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm">
            <Link href="/prospects" className="text-accent hover:underline">
              ← Prospects
            </Link>
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">{p.business_name}</h1>
          <p className="mt-1 break-all text-sm text-muted">
            {p.website_url && (
              <a
                href={p.website_url}
                target="_blank"
                rel="noreferrer noopener"
                className="text-accent hover:underline"
              >
                {p.verified_domain}
                {p.branch_key}
              </a>
            )}
            {p.industry && ` · ${p.industry}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge value={p.state} />
          {p.qualification_band && <Badge value={p.qualification_band} />}
        </div>
      </header>

      {user.role !== "READ_ONLY" && (
        <Card title="Review">
          <ProspectReview id={p.id} role={user.role} state={p.state} />
        </Card>
      )}

      <Card
        title="Qualification"
        actions={canAdmin ? <ActionButton path={`/prospects/${p.id}/qualify`} label="Re-score" /> : undefined}
      >
        {latest ? (
          <div className="grid gap-3 text-sm">
            <p>
              <Badge value={latest.outcome} />{" "}
              {latest.score !== null ? `${Number(latest.score).toFixed(0)}/100` : "no score"} from{" "}
              {Math.round(latest.evidence_coverage * 100)}% of the rubric (only components with evidence
              count) · {latest.reason_codes.join(", ")}
            </p>
            <ul className="grid gap-1.5">
              {Object.entries(latest.components).map(([k, c]) => (
                <li key={k} className="grid grid-cols-[11rem_5rem_1fr] gap-2">
                  <span className="text-muted">{COMPONENT_LABEL[k] ?? k}</span>
                  <span className="tabular-nums">
                    {c.score === null ? "unknown" : `${c.score}/${c.weight}`}
                  </span>
                  <span className="text-muted">{c.reason}</span>
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted">
              A score is evidence of fit, not buying intent, and never permission to email.
            </p>
          </div>
        ) : (
          <p className="text-sm text-muted">Not scored yet.</p>
        )}
      </Card>

      <Card
        title="Website audits"
        actions={
          canAdmin && p.website_url ? (
            <ActionButton path={`/prospects/${p.id}/audit`} label="Run audit" />
          ) : undefined
        }
      >
        {audits.ok && audits.data.length ? (
          <ul className="grid gap-2 text-sm">
            {audits.data.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-2">
                <Badge value={a.status} />
                <Link href={`/audits/${a.id}`} className="text-accent hover:underline">
                  {formatDate(a.finished_at ?? a.created_at)}
                </Link>
                {a.scores.overall != null && (
                  <span className="text-muted">overall {a.scores.overall}/100</span>
                )}
                {a.error_summary && <span className="text-muted">{a.error_summary}</span>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">
            Not audited yet. Audits run in an isolated browser and never submit forms.
          </p>
        )}
      </Card>

      <Card
        title="Design brief"
        actions={
          canAdmin ? (
            <ActionButton
              path={`/prospects/${p.id}/brief`}
              label="Generate brief"
              disabledReason={
                audits.ok && audits.data.some((a) => a.status === "SUCCEEDED")
                  ? undefined
                  : "Needs a successful audit first."
              }
            />
          ) : undefined
        }
      >
        {designs.ok && designs.data.length ? (
          <ul className="grid gap-2 text-sm">
            {designs.data.map((d) => (
              <li key={d.id} className="flex flex-wrap items-center gap-2">
                <Badge value={d.status} />
                <Link href={`/designs/${d.id}`} className="text-accent hover:underline">
                  Version {d.current_version}
                </Link>
                <span className="text-muted">{d.model}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">
            No brief yet. Briefs use only verified facts and audit findings, and need review before any
            concept is built.
          </p>
        )}
      </Card>

      <Card title="Source evidence (field-level provenance)">
        {facts.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] text-sm">
              <thead className="text-left text-muted">
                <tr>
                  <th scope="col" className="py-2 font-medium">
                    Fact
                  </th>
                  <th scope="col" className="py-2 font-medium">
                    Value
                  </th>
                  <th scope="col" className="py-2 font-medium">
                    Source
                  </th>
                  <th scope="col" className="py-2 font-medium">
                    Confidence
                  </th>
                  <th scope="col" className="py-2 font-medium">
                    Retrieved
                  </th>
                </tr>
              </thead>
              <tbody>
                {facts.map((f, i) => (
                  <tr key={i} className="border-t border-line align-top">
                    <td className="py-2">{f.fact_field}</td>
                    <td className="py-2 break-all">{f.safe_value}</td>
                    <td className="py-2">
                      {f.source_url ? (
                        <a
                          href={f.source_url}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="text-accent hover:underline"
                        >
                          {f.source_name}
                        </a>
                      ) : (
                        f.source_name
                      )}
                      <span className="block text-xs text-muted">
                        {f.verification_method} · terms {f.terms_version ?? "—"}
                      </span>
                    </td>
                    <td className="py-2 tabular-nums">{Number(f.confidence).toFixed(2)}</td>
                    <td className="py-2 text-muted">{formatDate(f.retrieved_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-muted">No stored facts.</p>
        )}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Website checks">
          <ul className="grid gap-2 text-sm">
            {verifications.map((v) => (
              <li key={v.id}>
                <Badge value={v.status} /> <span className="break-all">{v.final_url ?? v.domain}</span>
                <span className="block text-xs text-muted">
                  {formatDate(v.checked_at)} · {v.origin}
                  {v.reason_codes.length ? ` · ${v.reason_codes.map(reasonText).join(" ")}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Identifiers and campaigns">
          <ul className="grid gap-1 text-sm">
            {place_ids.map((i) => (
              <li key={i.place_id} className="font-mono text-xs">
                {i.provider}: {i.place_id} ({i.status.toLowerCase()})
              </li>
            ))}
            {campaigns.map((c) => (
              <li key={c.id}>
                <Link href={`/campaigns/${c.id}`} className="text-accent hover:underline">
                  {c.name}
                </Link>
              </li>
            ))}
            {merges.map((m, i) => (
              <li key={i} className="text-xs text-muted">
                Merge: {m.reason} ({formatDate(m.merged_at)})
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
