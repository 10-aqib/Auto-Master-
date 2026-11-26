import { ActionButton } from "@/components/action-button";
import { Badge } from "@/components/badge";
import { PreviewLinkButton } from "@/components/preview-link-button";
import { Card, formatDate } from "@/components/ui";
import type { Proposal } from "@/lib/designs";

/** Proposal PDFs and preview links for one design project. Nothing here sends email. */
export function ProposalsCard({
  designId,
  proposals,
  canAdmin,
  hasActiveConcept,
}: {
  designId: string;
  proposals: Proposal[];
  canAdmin: boolean;
  hasActiveConcept: boolean;
}) {
  return (
    <Card
      title="Proposal and preview"
      actions={
        canAdmin ? (
          <ActionButton
            path={`/designs/${designId}/proposal`}
            label={proposals.length ? "Regenerate proposal" : "Generate proposal"}
            disabledReason={hasActiveConcept ? undefined : "Approve a validated concept first."}
          />
        ) : undefined
      }
    >
      {proposals.length === 0 ? (
        <p className="text-sm text-muted">
          No proposal yet. The PDF uses the active concept&apos;s validated screenshots, dated audit
          observations and your developer details. Nothing is emailed.
        </p>
      ) : (
        <div className="grid gap-5">
          {proposals.map((p) => {
            const failed = p.checks.filter((c) => !c.ok);
            const live = p.status === "READY" && !p.deleted_at;
            return (
              <section
                key={p.id}
                aria-label={`Proposal version ${p.proposal_version}`}
                className="grid gap-2 border-t border-line pt-4 text-sm first:border-0 first:pt-0"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">Proposal v{p.proposal_version}</span>
                  <Badge
                    value={p.status === "READY" ? "SUCCEEDED" : p.status}
                    label={p.status.toLowerCase()}
                  />
                  <span className="text-muted">
                    {formatDate(p.generated_at)}
                    {p.page_count ? ` · ${p.page_count} pages` : ""}
                    {p.pdf_bytes ? ` · ${(p.pdf_bytes / 1_048_576).toFixed(1)} MB` : ""}
                    {p.expires_at ? ` · expires ${formatDate(p.expires_at)}` : ""}
                  </span>
                </div>
                {p.summary && <p>{p.summary}</p>}
                {failed.length > 0 && (
                  <p className="text-rose-700 dark:text-rose-300">
                    Checks failed: {failed.map((c) => c.code).join(", ")}
                  </p>
                )}
                {live && (
                  <div className="flex flex-wrap items-start gap-3">
                    <a
                      href={`/api/proposal-pdf/${p.id}`}
                      className="inline-flex min-h-10 items-center rounded-lg border border-line px-3 hover:bg-background"
                    >
                      Download PDF
                    </a>
                    {canAdmin && <PreviewLinkButton proposalId={p.id} />}
                    {canAdmin && (
                      <ActionButton
                        path={`/proposals/${p.id}/delete`}
                        label="Delete proposal"
                        variant="danger"
                        confirmText="Delete this PDF and revoke all of its preview links?"
                      />
                    )}
                  </div>
                )}
                {p.previews.length > 0 && (
                  <ul className="grid gap-1">
                    {p.previews.map((v) => (
                      <li key={v.id} className="flex flex-wrap items-center gap-2">
                        <Badge
                          value={v.status === "ACTIVE" ? "SUCCEEDED" : v.status}
                          label={`preview ${v.status.toLowerCase()}`}
                        />
                        <span className="text-muted">
                          created {formatDate(v.created_at)} · expires {formatDate(v.expires_at)} · opened{" "}
                          {v.access_count}×
                        </span>
                        {canAdmin && v.status === "ACTIVE" && (
                          <ActionButton path={`/previews/${v.id}/revoke`} label="Revoke" variant="danger" />
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            );
          })}
        </div>
      )}
    </Card>
  );
}
