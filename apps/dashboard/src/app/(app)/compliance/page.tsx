import { ActionButton } from "@/components/action-button";
import { Badge } from "@/components/badge";
import { JsonForm } from "@/components/json-form";
import { Alert, Card, Field, formatDate } from "@/components/ui";
import { CountryPauseForm, PolicyDraftForm } from "@/components/compliance-forms";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import { type Policy, type SuppressionSummary } from "@/lib/outreach";

export const metadata = { title: "Compliance · WEBFORGE AI" };

interface EmailConfig {
  provider: string;
  is_mock: boolean;
  live_sending_enabled: boolean;
  sender_configured: boolean;
  physical_address_configured: boolean;
  daily_max: number;
  hourly_max: number;
}

export default async function CompliancePage() {
  const { user } = await requireActiveSession();
  const [policies, suppressions, config] = await Promise.all([
    apiServer<Policy[]>("/compliance/policies"),
    apiServer<SuppressionSummary>("/compliance/suppressions"),
    apiServer<EmailConfig>("/outreach/config"),
  ]);
  const canAdmin = user.role === "OWNER" || user.role === "ADMIN";
  const owner = user.role === "OWNER";

  return (
    <div className="grid gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Email compliance</h1>
        <p className="mt-1 text-sm text-muted">
          Engineering controls, not legal advice. Every country, recipient type and message category stays on
          hold until a policy reviewed by qualified counsel is active.
        </p>
      </header>

      {config.ok && (
        <Card title="Sending status">
          <ul className="grid gap-1 text-sm">
            <li>
              Provider: <strong>{config.data.provider}</strong>{" "}
              {config.data.is_mock ? "(mock — nothing leaves this system)" : ""}
            </li>
            <li>Live sending: {config.data.live_sending_enabled ? "enabled" : "disabled"}</li>
            <li>
              Sender identity configured:{" "}
              {config.data.sender_configured ? "yes" : "no (EMAIL_FROM_ADDRESS / EMAIL_REPLY_TO)"}
            </li>
            <li>
              Postal address configured:{" "}
              {config.data.physical_address_configured ? "yes" : "no (EMAIL_PHYSICAL_ADDRESS)"}
            </li>
            <li>
              Limits: {config.data.daily_max}/day, {config.data.hourly_max}/hour{" "}
              {config.data.daily_max === 0 ? "(0 blocks every send)" : ""}
            </li>
          </ul>
          <p className="mt-2 text-xs text-muted">
            Resend and Postmark prohibit unsolicited email in their current terms, so no live adapter is
            enabled. See docs/compliance/email-providers.md.
          </p>
        </Card>
      )}

      <Card title="Country policy registry">
        {!policies.ok ? (
          <Alert>{policies.error.message}</Alert>
        ) : policies.data.length === 0 ? (
          <p className="text-sm text-muted">
            No policies. Without an active reviewed policy, every message is held.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[44rem] text-sm">
              <thead className="text-left text-muted">
                <tr>
                  <th scope="col" className="py-2 font-medium">
                    Country / type
                  </th>
                  <th scope="col" className="py-2 font-medium">
                    Version
                  </th>
                  <th scope="col" className="py-2 font-medium">
                    Status
                  </th>
                  <th scope="col" className="py-2 font-medium">
                    Review
                  </th>
                  <th scope="col" className="py-2 font-medium">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {policies.data.map((p) => (
                  <tr key={p.id} className="border-t border-line align-top">
                    <td className="py-2">
                      {p.country_code} · {p.recipient_type.toLowerCase()}
                      <div className="text-xs text-muted">{p.message_category}</div>
                    </td>
                    <td className="py-2">{p.version}</td>
                    <td className="py-2">
                      <Badge
                        value={
                          p.status === "ACTIVE" ? "SUCCEEDED" : p.status === "RETIRED" ? "CANCELLED" : "DRAFT"
                        }
                        label={p.status.toLowerCase()}
                      />
                      {p.rules.permitted === false && <div className="text-xs text-muted">not permitted</div>}
                    </td>
                    <td className="py-2 text-xs">
                      {p.reviewer_name
                        ? `${p.reviewer_name} (${p.reviewer_qualification}), ${formatDate(p.reviewed_at)}`
                        : "Not reviewed"}
                      <div className="text-muted">next review {String(p.rules.next_review ?? "—")}</div>
                    </td>
                    <td className="py-2">
                      {owner && (p.status === "DRAFT" || p.status === "IN_REVIEW") && (
                        <details>
                          <summary className="cursor-pointer text-accent">
                            Record legal review and activate
                          </summary>
                          <JsonForm
                            path={`/compliance/policies/${p.id}/activate`}
                            submitLabel="Activate policy"
                            className="mt-2 grid gap-2"
                            confirmText="Confirm that qualified counsel reviewed this exact policy."
                          >
                            <Field id={`rn-${p.id}`} name="reviewer_name" label="Reviewer name" />
                            <Field
                              id={`rq-${p.id}`}
                              name="reviewer_qualification"
                              label="Reviewer qualification"
                            />
                            <Field id={`rd-${p.id}`} name="reviewed_on" label="Reviewed on" type="date" />
                            <Field
                              id={`ef-${p.id}`}
                              name="effective_from"
                              label="Effective from"
                              type="date"
                            />
                          </JsonForm>
                        </details>
                      )}
                      {canAdmin && p.status === "ACTIVE" && (
                        <ActionButton
                          path={`/compliance/policies/${p.id}/retire`}
                          label="Retire"
                          variant="danger"
                          confirmText="Retire this policy? Matching messages will be held."
                        />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {canAdmin && (
          <details className="mt-4 text-sm">
            <summary className="cursor-pointer text-accent">Add a policy draft</summary>
            <PolicyDraftForm />
          </details>
        )}
      </Card>

      <Card title="Suppression list">
        {suppressions.ok && (
          <div className="grid gap-2 text-sm">
            <p>
              {suppressions.data.total} suppressed address{suppressions.data.total === 1 ? "" : "es"}
              {Object.entries(suppressions.data.by_reason).map(
                ([k, v]) => ` · ${k.toLowerCase().replaceAll("_", " ")} ${v}`,
              )}
            </p>
            <p className="text-xs text-muted">{suppressions.data.note}</p>
          </div>
        )}
        {canAdmin && (
          <JsonForm
            path="/compliance/suppressions"
            submitLabel="Suppress address"
            className="mt-3 grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end"
            confirmText="Add this address to the global suppression list? This cannot be undone here."
          >
            <Field
              id="sup-email"
              name="email"
              label="Email address to suppress"
              type="email"
              autoComplete="off"
            />
          </JsonForm>
        )}
      </Card>

      {canAdmin && (
        <Card title="Scoped pause switches">
          <p className="mb-3 text-sm text-muted">
            Hold all email for one country or one provider. Global and email pauses are in Settings.
          </p>
          <CountryPauseForm />
          <p className="mt-2 text-xs text-muted">
            Resuming a scoped pause is owner-only and done from Settings.
          </p>
        </Card>
      )}
    </div>
  );
}
