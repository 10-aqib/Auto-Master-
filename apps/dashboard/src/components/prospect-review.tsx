"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Alert, Button, Field } from "@/components/ui";
import { api } from "@/lib/api-client";
import type { Role } from "@/lib/auth-shared";

const DECISIONS: { value: string; label: string; roles: Role[] }[] = [
  { value: "approve", label: "Approve (qualified)", roles: ["OWNER", "ADMIN", "REVIEWER"] },
  { value: "hold", label: "Hold for review", roles: ["OWNER", "ADMIN", "REVIEWER"] },
  { value: "reject", label: "Reject", roles: ["OWNER", "ADMIN", "REVIEWER"] },
  { value: "do_not_contact", label: "Do not contact (global)", roles: ["OWNER", "ADMIN", "REVIEWER"] },
  { value: "reopen", label: "Reopen", roles: ["OWNER", "ADMIN"] },
];

export function ProspectReview({ id, role, state }: { id: string; role: Role; state: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const options = DECISIONS.filter((d) => d.roles.includes(role)).filter((d) =>
    d.value === "reopen"
      ? state === "REJECTED" || (state === "DO_NOT_CONTACT" && role === "OWNER")
      : state !== "DO_NOT_CONTACT",
  );

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const decision = String(form.get("decision"));
    if (
      decision === "do_not_contact" &&
      !window.confirm("Mark as do-not-contact everywhere? Only the owner can undo this.")
    )
      return;
    setBusy(true);
    setError(null);
    const r = await api(`/prospects/${id}/review`, "POST", {
      decision,
      reason: String(form.get("reason") ?? ""),
    });
    setBusy(false);
    if (!r.ok) return setError(r.error.message);
    router.refresh();
  }

  if (!options.length)
    return <p className="text-sm text-muted">No review actions are available for this state.</p>;
  return (
    <form onSubmit={onSubmit} className="grid gap-3 sm:grid-cols-[14rem_1fr_auto] sm:items-end" noValidate>
      <label className="grid gap-1.5 text-sm font-medium">
        Decision
        <select
          name="decision"
          className="min-h-10 rounded-lg border border-line bg-background px-3 font-normal"
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      <Field id="review-reason" name="reason" label="Reason (recorded in the activity log)" required />
      <Button type="submit" busy={busy}>
        Save decision
      </Button>
      {error && (
        <div className="sm:col-span-3">
          <Alert>{error}</Alert>
        </div>
      )}
    </form>
  );
}
