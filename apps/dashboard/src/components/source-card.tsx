"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { UsageMeter } from "@/components/usage-meter";
import { Alert, Button, Card, Field, formatDate } from "@/components/ui";
import { api } from "@/lib/api-client";
import type { Role } from "@/lib/auth-shared";
import type { Source } from "@/lib/sources";

function StatusPill({ source }: { source: Source }) {
  const [label, tone] = source.usable
    ? ["Usable", "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 ring-emerald-500/30"]
    : source.status === "ENABLED"
      ? ["Enabled, blocked", "bg-amber-500/15 text-amber-800 dark:text-amber-300 ring-amber-500/30"]
      : ["Disabled", "bg-background text-muted ring-line"];
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${tone}`}>
      {label}
    </span>
  );
}

export function SourceCard({ source, role }: { source: Source; role: Role }) {
  const router = useRouter();
  const [mode, setMode] = useState<"idle" | "review" | "status">("idle");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const isOwner = role === "OWNER";
  const isMock = source.source_type === "MOCK";
  const enabling = source.status === "DISABLED";
  const canToggle = enabling ? isOwner : true;
  const needsReview = !isMock && !source.terms_reviewed_at;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    setFieldErrors({});
    const r =
      mode === "review"
        ? await api<Source>(`/sources/${source.key}/review`, "POST", {
            terms_url: String(form.get("terms_url") ?? ""),
            terms_version: String(form.get("terms_version") ?? ""),
            review_notes: String(form.get("review_notes") ?? ""),
          })
        : await api<Source>(`/sources/${source.key}/${enabling ? "enable" : "disable"}`, "POST", {
            reason: String(form.get("reason") ?? ""),
          });
    setBusy(false);
    if (!r.ok) {
      setError(r.error.message);
      setFieldErrors(r.error.field_errors);
      return;
    }
    setMode("idle");
    router.refresh();
  }

  return (
    <Card title={source.display_name} actions={<StatusPill source={source} />}>
      <div className="grid gap-4 text-sm">
        <p className="text-muted">{source.description}</p>
        <dl className="grid gap-x-4 gap-y-1.5 sm:grid-cols-[11rem_1fr]">
          <dt className="text-muted">May be stored</dt>
          <dd>{source.persistable_fields.length ? source.persistable_fields.join(", ") : "nothing"}</dd>
          <dt className="text-muted">Cache limits</dt>
          <dd>
            {Object.keys(source.cache_rules).length
              ? Object.entries(source.cache_rules)
                  .map(([f, s]) => `${f}: ${Math.round(s / 86400)} days`)
                  .join(", ")
              : "no caching"}
          </dd>
          <dt className="text-muted">Attribution</dt>
          <dd>{source.attribution_required ? source.attribution_text : "not required"}</dd>
          <dt className="text-muted">Terms review</dt>
          <dd>
            {isMock
              ? "not applicable (test data)"
              : source.terms_reviewed_at
                ? `${source.terms_version} · ${formatDate(source.terms_reviewed_at)}`
                : "not reviewed"}
          </dd>
          {source.status_reason && (
            <>
              <dt className="text-muted">Last change</dt>
              <dd>
                {source.status_reason} · {formatDate(source.status_changed_at)}
              </dd>
            </>
          )}
        </dl>

        {source.policy_urls.length > 0 && (
          <details>
            <summary className="cursor-pointer text-accent">
              Policies checked ({source.policy_urls.length})
            </summary>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">
              {source.policy_urls.map((u) => (
                <li key={u} className="break-all">
                  <a
                    href={u}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-accent hover:underline"
                  >
                    {u}
                  </a>
                </li>
              ))}
            </ul>
          </details>
        )}

        {source.blockers.length > 0 && (
          <Alert tone="info">
            <p className="font-medium">Not usable yet:</p>
            <ul className="mt-1 list-disc pl-5">
              {source.blockers.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </Alert>
        )}

        {source.usage && <UsageMeter usage={source.usage} />}

        {mode === "idle" ? (
          <div className="flex flex-wrap gap-2">
            {isOwner && !isMock && (
              <Button type="button" variant="secondary" onClick={() => setMode("review")}>
                {source.terms_reviewed_at ? "Update terms review" : "Record terms review"}
              </Button>
            )}
            <Button
              type="button"
              variant={enabling ? "primary" : "danger"}
              disabled={!canToggle || (enabling && needsReview)}
              title={
                !canToggle
                  ? "Only the owner can enable sources."
                  : enabling && needsReview
                    ? "Record a terms review first."
                    : undefined
              }
              onClick={() => setMode("status")}
            >
              {enabling ? "Enable" : "Disable"}
            </Button>
            {enabling && needsReview && (
              <p className="self-center text-xs text-muted">Record a terms review first.</p>
            )}
            {enabling && !isOwner && (
              <p className="self-center text-xs text-muted">Only the owner can enable sources.</p>
            )}
          </div>
        ) : (
          <form onSubmit={submit} className="grid gap-3" noValidate>
            {error && <Alert>{error}</Alert>}
            {mode === "review" ? (
              <>
                <Field
                  id={`${source.key}-url`}
                  name="terms_url"
                  label="Terms URL (https)"
                  defaultValue={source.terms_url ?? ""}
                  error={fieldErrors.terms_url}
                  required
                />
                <Field
                  id={`${source.key}-version`}
                  name="terms_version"
                  label="Version or date reviewed"
                  defaultValue={source.terms_version ?? ""}
                  error={fieldErrors.terms_version}
                  required
                />
                <div className="grid gap-1.5">
                  <label htmlFor={`${source.key}-notes`} className="text-sm font-medium">
                    What you checked and decided
                  </label>
                  <textarea
                    id={`${source.key}-notes`}
                    name="review_notes"
                    rows={4}
                    minLength={20}
                    defaultValue={source.review_notes ?? ""}
                    className="rounded-lg border border-line bg-background px-3 py-2 text-sm"
                    required
                  />
                  {fieldErrors.review_notes && (
                    <p className="text-xs text-rose-700 dark:text-rose-300">{fieldErrors.review_notes}</p>
                  )}
                </div>
              </>
            ) : (
              <Field
                id={`${source.key}-reason`}
                name="reason"
                label={`Reason to ${enabling ? "enable" : "disable"}`}
                error={fieldErrors.reason}
                required
              />
            )}
            <div className="flex flex-wrap gap-2">
              <Button
                type="submit"
                busy={busy}
                variant={mode === "status" && !enabling ? "danger" : "primary"}
              >
                {mode === "review" ? "Save review" : enabling ? "Enable source" : "Disable source"}
              </Button>
              <Button type="button" variant="secondary" onClick={() => setMode("idle")}>
                Cancel
              </Button>
            </div>
          </form>
        )}
      </div>
    </Card>
  );
}
