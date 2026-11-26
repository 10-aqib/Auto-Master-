import Link from "next/link";

import { Badge } from "@/components/badge";
import { ActionButton } from "@/components/action-button";
import { ReviewForm } from "@/components/brief-review";
import { ConceptPreview } from "@/components/concept-preview";
import { Alert, Card, formatDate } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import { ProposalsCard } from "@/components/proposals-card";
import { ValidationReport } from "@/components/validation-report";
import {
  KIND_LABEL,
  formatCost,
  type Brief,
  type DesignDetail,
  type Proposal,
  type Render,
  type Validation,
} from "@/lib/designs";

export const metadata = { title: "Design brief · WEBFORGE AI" };

function BriefBody({ brief }: { brief: Brief }) {
  const b = brief.brief;
  if (!b) return <p className="text-sm text-muted">No valid brief was produced for this version.</p>;
  const facts = new Map(brief.facts_snapshot.facts.map((f) => [f.id, f]));
  return (
    <div className="grid gap-5 text-sm">
      <div className="grid gap-1">
        <h3 className="font-medium">Summary</h3>
        <p>{b.business_summary}</p>
        <p className="text-muted">
          {b.design_direction.positioning} Tone: {b.design_direction.tone}.
        </p>
      </div>

      <div className="grid gap-2">
        <h3 className="font-medium">Palette and type</h3>
        <ul className="flex flex-wrap gap-3">
          {Object.entries(b.palette).map(([name, hex]) => (
            <li key={name} className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className="inline-block size-5 rounded border border-line"
                style={{ backgroundColor: hex }}
              />
              <span className="text-muted">
                {name.replaceAll("_", " ")} {hex}
              </span>
            </li>
          ))}
        </ul>
        <p className="text-muted">
          Headings: {b.typography.heading} · Body: {b.typography.body}
        </p>
      </div>

      <div className="grid gap-3">
        <h3 className="font-medium">Six screens</h3>
        {b.pages.map((page) => (
          <section key={page.slug} className="rounded-lg border border-line p-3">
            <h4 className="font-medium">
              {page.title} <span className="text-muted">/{page.slug}</span>
            </h4>
            <p className="text-muted">{page.goal}</p>
            <ul className="mt-2 grid gap-2">
              {page.sections.map((s, i) => (
                <li key={i} className="grid gap-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{s.heading}</span>
                    <span className="text-xs text-muted">{s.block}</span>
                    <Badge
                      value={s.content_kind === "assumption" ? "HOLD" : "DRAFT"}
                      label={KIND_LABEL[s.content_kind]}
                    />
                  </div>
                  <p>{s.body}</p>
                  {s.items.length > 0 && (
                    <ul className="list-disc pl-5 text-muted">
                      {s.items.map((it, k) => (
                        <li key={k}>
                          {it.title}: {it.text}
                        </li>
                      ))}
                    </ul>
                  )}
                  {s.fact_ids.length > 0 && (
                    <p className="text-xs text-muted">
                      Sources:{" "}
                      {s.fact_ids.map((id) => `${id} (${facts.get(id)?.field ?? "unknown"})`).join(", ")}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      {b.assumptions.length > 0 && (
        <div className="grid gap-1">
          <h3 className="font-medium">Assumptions to confirm</h3>
          <ul className="list-disc pl-5">
            {b.assumptions.map((a, i) => (
              <li key={i}>{a.statement}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function RenderCard({
  render: r,
  canReview,
  canAdmin,
  validation,
}: {
  render: Render;
  canReview: boolean;
  canAdmin: boolean;
  validation: Validation | undefined;
}) {
  const ready = validation?.status === "READY";
  return (
    <section
      className="grid gap-3 border-t border-line pt-4 first:border-0 first:pt-0"
      aria-label={`Concept version ${r.version}`}
    >
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">Concept v{r.version}</span>
        <Badge value={r.status} />
        {r.is_active && <Badge value="ACTIVE" label="active" />}
        <span className="text-muted">
          {formatDate(r.created_at)} · brief v{r.manifest.brief_version} · {r.renderer_version} · {r.variant}{" "}
          style
          {r.manifest.safe_mode ? " · safe-mode repair" : ""}
        </span>
      </div>
      {r.scan_issues.length > 0 && (
        <Alert>
          <span className="font-medium">Safety or integrity checks failed; nothing was published:</span>
          <ul className="mt-1 list-disc pl-5">
            {r.scan_issues.slice(0, 20).map((i, k) => (
              <li key={k}>
                {i.code}
                {i.page ? ` (${i.page})` : ""}: {i.detail}
              </li>
            ))}
          </ul>
        </Alert>
      )}
      {r.manifest.pages.length > 0 && <ConceptPreview renderId={r.id} pages={r.manifest.pages} />}
      {r.manifest.assets.length > 0 && (
        <p className="text-xs text-muted">
          Assets: {r.manifest.assets.map((a) => `${a.key.split("/").pop()} (${a.license})`).join(", ")} ·
          fonts: system stacks only
        </p>
      )}
      {validation ? (
        <ValidationReport validation={validation} />
      ) : (
        r.status !== "FAILED" && (
          <p className="text-sm text-muted">
            Validation is queued: every page is checked offline at desktop, tablet and mobile widths.
          </p>
        )
      )}
      {canAdmin && validation && r.status !== "FAILED" && r.status !== "REJECTED" && (
        <div>
          <ActionButton path={`/designs/renders/${r.id}/validate`} label="Re-run validation" />
        </div>
      )}
      {r.review_notes && <p className="text-sm text-muted">Review notes: {r.review_notes}</p>}
      {canReview && r.status === "RENDERED" && (
        <ReviewForm
          id={r.id}
          path={`/designs/renders/${r.id}/review`}
          subject="concept"
          approvable={ready}
          blockedReason="Approval needs a READY validation with no critical failures."
        />
      )}
      {canAdmin && r.status === "APPROVED" && !r.is_active && (
        <div>
          <ActionButton path={`/designs/renders/${r.id}/activate`} label="Make active (roll back)" />
        </div>
      )}
    </section>
  );
}

export default async function DesignPage({ params }: PageProps<"/designs/[id]">) {
  const { id } = await params;
  const { user } = await requireActiveSession();
  const [detail, proposals] = await Promise.all([
    apiServer<DesignDetail>(`/designs/${id}`),
    apiServer<Proposal[]>(`/proposals?design_id=${id}`),
  ]);
  if (!detail.ok) return <Alert>{detail.error.message}</Alert>;
  const { project, briefs, renders, validations } = detail.data;
  const canReview = user.role !== "READ_ONLY";
  const canAdmin = user.role === "OWNER" || user.role === "ADMIN";
  const hasApprovedBrief = briefs.some((b) => b.status === "APPROVED");

  return (
    <div className="grid gap-6">
      <header>
        <p className="text-sm">
          <Link href={`/prospects/${project.prospect_id}`} className="text-accent hover:underline">
            ← Prospect
          </Link>
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Design brief and concept</h1>
        <p className="mt-1 text-sm text-muted">
          Independent redesign concept plan. Not the business&apos;s official website. Every factual section
          cites a verified source; everything else is labelled as proposed copy or an assumption.
        </p>
      </header>

      <ProposalsCard
        designId={project.id}
        proposals={proposals.ok ? proposals.data : []}
        canAdmin={canAdmin}
        hasActiveConcept={renders.some((r) => r.is_active && r.status === "APPROVED")}
      />

      <Card
        title="Six-screen concepts"
        actions={
          canAdmin ? (
            <ActionButton
              path={`/designs/${project.id}/render`}
              label="Render concept"
              disabledReason={hasApprovedBrief ? undefined : "Approve a brief first."}
            />
          ) : undefined
        }
      >
        {renders.length ? (
          <div className="grid gap-6">
            {renders.map((r) => (
              <RenderCard
                key={r.id}
                render={r}
                canReview={canReview}
                canAdmin={canAdmin}
                validation={validations.find((v) => v.render_id === r.id)}
              />
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted">
            No concept yet. Rendering turns the approved brief into six static, script-free pages.
          </p>
        )}
      </Card>

      {briefs.length === 0 && <p className="text-sm text-muted">No brief versions yet.</p>}

      {briefs.map((brief) => (
        <Card key={brief.id} title={`Version ${brief.version}`} actions={<Badge value={brief.status} />}>
          <div className="grid gap-4">
            <p className="text-xs text-muted">
              {formatDate(brief.created_at)} · {brief.model} · {brief.attempts} attempt(s) ·{" "}
              {brief.input_tokens + brief.output_tokens} tokens · {formatCost(brief.cost_milliminor)} · schema{" "}
              {brief.schema_version} · prompt {brief.prompt_version}
            </p>
            {brief.validation_issues.length > 0 && (
              <Alert>
                <span className="font-medium">Checks that failed:</span>
                <ul className="mt-1 list-disc pl-5">
                  {brief.validation_issues.slice(0, 20).map((i, k) => (
                    <li key={k}>
                      {i.code} at {i.location}: {i.detail}
                    </li>
                  ))}
                </ul>
              </Alert>
            )}
            <BriefBody brief={brief} />
            {brief.review_notes && <p className="text-sm text-muted">Review notes: {brief.review_notes}</p>}
            {canReview && (brief.status === "DRAFT" || brief.status === "NEEDS_REVIEW") && (
              <ReviewForm
                id={brief.id}
                path={`/designs/briefs/${brief.id}/review`}
                subject="brief"
                approvable={brief.status === "DRAFT" && brief.brief !== null}
                blockedReason="This version has open issues and cannot be approved. Regenerate it or reject it."
              />
            )}
          </div>
        </Card>
      ))}
    </div>
  );
}
