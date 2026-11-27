"use client";

import { ActionButton } from "@/components/action-button";
import { Badge } from "@/components/badge";
import { JsonForm, Select, TextArea } from "@/components/json-form";
import { Card, Field, formatDate } from "@/components/ui";
import type { Proposal } from "@/lib/designs";
import { CHECK_LABEL, type Contact, type OutreachMessage } from "@/lib/outreach";

const RECIPIENT_TYPES = ["CORPORATE", "ROLE_ACCOUNT", "SOLE_TRADER", "INDIVIDUAL", "UNKNOWN"];
const BASES = [
  { value: "", label: "Not recorded" },
  { value: "legitimate_interest", label: "Legitimate interest (as reviewed)" },
  { value: "corporate_subscriber_exemption", label: "Corporate subscriber exemption (as reviewed)" },
  { value: "consent", label: "Consent (record evidence on the contact)" },
  { value: "existing_relationship", label: "Existing relationship" },
  { value: "none_required_reviewed", label: "None required (counsel reviewed)" },
];

function MessageView({ m, role, devSimulate }: { m: OutreachMessage; role: string; devSimulate: boolean }) {
  const a = m.assessment;
  const owner = role === "OWNER";
  return (
    <section
      aria-label={`Outreach message ${m.subject ?? ""}`}
      className="grid gap-3 rounded-lg border border-line p-3 text-sm"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          value={
            m.status === "ACCEPTED" || m.status === "DELIVERED"
              ? "SUCCEEDED"
              : m.status === "PENDING_REVIEW"
                ? "QUEUED"
                : m.status
          }
          label={m.status.toLowerCase().replaceAll("_", " ")}
        />
        {a && (
          <Badge
            value={a.decision === "ELIGIBLE" ? "SUCCEEDED" : a.decision === "HOLD" ? "HOLD" : "FAILED"}
            label={`compliance ${a.decision.toLowerCase()}`}
          />
        )}
        <span className="text-muted">
          {m.provider} · created {formatDate(m.created_at)}
          {m.accepted_at ? ` · accepted ${formatDate(m.accepted_at)}` : ""}
          {m.error_code ? ` · ${m.error_code}` : ""}
          {m.cancelled_reason ? ` · ${m.cancelled_reason}` : ""}
        </span>
      </div>
      {a && (
        <details open={a.decision !== "ELIGIBLE"}>
          <summary className="cursor-pointer font-medium">
            Pre-send checks ({a.checks.filter((c) => c.ok).length}/{a.checks.length} pass)
          </summary>
          <ol className="mt-2 grid gap-1">
            {a.checks.map((c, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2">
                <Badge
                  value={c.ok ? "SUCCEEDED" : c.severity === "ineligible" ? "FAILED" : "HOLD"}
                  label={c.ok ? "pass" : c.severity}
                />
                <span>
                  {c.n}. {CHECK_LABEL[c.code] ?? c.code}
                  {!c.ok && c.reason ? ` — ${c.reason}` : ""}
                  {c.detail ? <span className="text-muted"> ({c.detail})</span> : null}
                </span>
              </li>
            ))}
          </ol>
        </details>
      )}
      {m.body && (
        <details>
          <summary className="cursor-pointer font-medium">Message: {m.subject}</summary>
          <pre className="mt-2 whitespace-pre-wrap break-words rounded bg-background p-3 font-sans text-sm">
            {m.body}
          </pre>
        </details>
      )}
      <div className="flex flex-wrap gap-2">
        {(m.status === "DRAFT" || m.status === "PENDING_REVIEW") &&
          role !== "READ_ONLY" &&
          role !== "REVIEWER" && <ActionButton path={`/outreach/${m.id}/reassess`} label="Re-run checks" />}
        {m.status === "PENDING_REVIEW" && (
          <ActionButton
            path={`/outreach/${m.id}/approve`}
            label="Approve and send"
            variant="primary"
            confirmText="Send this one message now through the configured provider? Every check runs again first."
            disabledReason={owner ? undefined : "Only the owner can approve sending."}
          />
        )}
        {["DRAFT", "PENDING_REVIEW", "SCHEDULED"].includes(m.status) &&
          (role === "OWNER" || role === "ADMIN") && (
            <ActionButton path={`/outreach/${m.id}/cancel`} label="Cancel" variant="danger" />
          )}
        {devSimulate && owner && m.provider_message_id && (
          <>
            <ActionButton
              path={`/outreach/${m.id}/simulate`}
              body={{ kind: "delivered" }}
              label="Simulate delivered"
            />
            <ActionButton
              path={`/outreach/${m.id}/simulate`}
              body={{ kind: "reply", text: "Thanks, this looks good. Can we talk next week?" }}
              label="Simulate reply"
            />
            <ActionButton
              path={`/outreach/${m.id}/simulate`}
              body={{ kind: "hard_bounce" }}
              label="Simulate bounce"
              variant="danger"
            />
          </>
        )}
      </div>
    </section>
  );
}

export function OutreachCard({
  prospectId,
  contacts,
  messages,
  proposals,
  role,
  devSimulate,
}: {
  prospectId: string;
  contacts: Contact[];
  messages: OutreachMessage[];
  proposals: Proposal[];
  role: string;
  devSimulate: boolean;
}) {
  const canAdmin = role === "OWNER" || role === "ADMIN";
  const ready = proposals.filter((p) => p.status === "READY" && !p.deleted_at);
  const usable = contacts.filter((c) => !c.suppressed);
  return (
    <Card title="Outreach (compliance-checked, one message only)">
      <div className="grid gap-5 text-sm">
        <p className="text-muted">
          A published address is contact data, not consent. Every message passes 17 checks before it can be
          approved and again right before sending. Unknown or unreviewed cases stay on hold.
        </p>

        <div className="grid gap-2">
          <h3 className="font-medium">Contacts</h3>
          {contacts.length ? (
            <ul className="grid gap-1">
              {contacts.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center gap-2">
                  <span className="font-mono">{c.email_masked}</span>
                  <span className="text-muted">
                    {c.recipient_type.toLowerCase()} · {c.country_code ?? "country unknown"} ·{" "}
                    {c.verification_method}
                  </span>
                  {c.suppressed && <Badge value="FAILED" label="suppressed" />}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted">No contacts recorded.</p>
          )}
          {canAdmin && (
            <details>
              <summary className="cursor-pointer text-accent">Add a contact</summary>
              <JsonForm
                path={`/prospects/${prospectId}/contacts`}
                submitLabel="Save contact"
                className="mt-3 grid gap-3 sm:grid-cols-2"
                transform={(b) => ({
                  email: b.email,
                  recipient_type: b.recipient_type,
                  country_code: b.country_code ? b.country_code.toUpperCase() : null,
                  source_url: b.source_url,
                  verification_method: b.verification_method,
                  contact_name: b.contact_name || null,
                })}
              >
                <Field id="ct-email" name="email" label="Email address" type="email" autoComplete="off" />
                <Select
                  label="Recipient type"
                  name="recipient_type"
                  options={RECIPIENT_TYPES.map((t) => ({
                    value: t,
                    label: t.toLowerCase().replaceAll("_", " "),
                  }))}
                />
                <Field id="ct-country" name="country_code" label="Country (ISO code)" maxLength={2} />
                <Field
                  id="ct-source"
                  name="source_url"
                  label="Page where it is published (https)"
                  hint="Must be on the prospect's verified domain."
                />
                <Select
                  label="How it was obtained"
                  name="verification_method"
                  options={[
                    { value: "published_on_official_website", label: "Published on the official website" },
                    { value: "provided_by_business", label: "Provided by the business" },
                  ]}
                />
                <Field id="ct-name" name="contact_name" label="Contact name (only if published)" />
              </JsonForm>
            </details>
          )}
        </div>

        <div className="grid gap-2">
          <h3 className="font-medium">Messages</h3>
          {messages.length ? (
            messages.map((m) => <MessageView key={m.id} m={m} role={role} devSimulate={devSimulate} />)
          ) : (
            <p className="text-muted">No message drafted.</p>
          )}
          {canAdmin &&
            messages.every((m) => ["CANCELLED", "FAILED"].includes(m.status)) &&
            (ready.length && usable.length ? (
              <details>
                <summary className="cursor-pointer text-accent">Draft the initial message</summary>
                <JsonForm
                  path={`/prospects/${prospectId}/outreach`}
                  submitLabel="Draft and check"
                  className="mt-3 grid gap-3"
                  transform={(b) => ({
                    contact_id: b.contact_id,
                    proposal_id: b.proposal_id,
                    legal_basis: b.legal_basis || null,
                    legal_basis_evidence: b.legal_basis_evidence || null,
                  })}
                >
                  <Select
                    label="Contact"
                    name="contact_id"
                    options={usable.map((c) => ({
                      value: c.id,
                      label: `${c.email_masked} (${c.recipient_type.toLowerCase()})`,
                    }))}
                  />
                  <Select
                    label="Proposal"
                    name="proposal_id"
                    options={ready.map((p) => ({ value: p.id, label: `Proposal v${p.proposal_version}` }))}
                  />
                  <Select label="Legal basis (as reviewed by counsel)" name="legal_basis" options={BASES} />
                  <TextArea
                    label="Evidence for that basis"
                    name="legal_basis_evidence"
                    rows={3}
                    hint="Reference the counsel review or consent record. Required for eligibility."
                  />
                </JsonForm>
              </details>
            ) : (
              <p className="text-muted">
                Needs a READY proposal and an unsuppressed contact before drafting.
              </p>
            ))}
        </div>
      </div>
    </Card>
  );
}
