import Link from "next/link";

import { Badge } from "@/components/badge";
import { BriefReview } from "@/components/brief-review";
import { Alert, Card, formatDate } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import { KIND_LABEL, formatCost, type Brief, type DesignDetail } from "@/lib/designs";

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

export default async function DesignPage({ params }: PageProps<"/designs/[id]">) {
  const { id } = await params;
  const { user } = await requireActiveSession();
  const detail = await apiServer<DesignDetail>(`/designs/${id}`);
  if (!detail.ok) return <Alert>{detail.error.message}</Alert>;
  const { project, briefs } = detail.data;
  const canReview = user.role !== "READ_ONLY";

  return (
    <div className="grid gap-6">
      <header>
        <p className="text-sm">
          <Link href={`/prospects/${project.prospect_id}`} className="text-accent hover:underline">
            ← Prospect
          </Link>
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Design brief</h1>
        <p className="mt-1 text-sm text-muted">
          Independent redesign concept plan. Not the business&apos;s official website. Every factual section
          cites a verified source; everything else is labelled as proposed copy or an assumption.
        </p>
      </header>

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
              <BriefReview id={brief.id} approvable={brief.status === "DRAFT" && brief.brief !== null} />
            )}
          </div>
        </Card>
      ))}
    </div>
  );
}
