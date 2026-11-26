"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Button, Field } from "@/components/ui";
import { api } from "@/lib/api-client";

/** Approve or reject one brief version. Only valid drafts can be approved (enforced by the API). */
export function BriefReview({ id, approvable }: { id: string; approvable: boolean }) {
  const router = useRouter();
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function decide(approve: boolean) {
    if (!approve && !window.confirm("Reject this brief version?")) return;
    setBusy(true);
    setError(null);
    const r = await api(`/designs/briefs/${id}/review`, "POST", { approve, notes });
    setBusy(false);
    if (!r.ok) return setError(r.error.message);
    router.refresh();
  }

  return (
    <div className="grid gap-3">
      <Field
        id={`notes-${id}`}
        label="Review notes"
        name="notes"
        maxLength={2000}
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          busy={busy}
          disabled={!approvable}
          title={approvable ? undefined : "Only drafts that passed every check can be approved."}
          onClick={() => decide(true)}
        >
          Approve brief
        </Button>
        <Button type="button" variant="danger" busy={busy} onClick={() => decide(false)}>
          Reject brief
        </Button>
      </div>
      {!approvable && (
        <p className="text-xs text-muted">
          This version has open issues and cannot be approved. Regenerate it or reject it.
        </p>
      )}
      {error && <Alert>{error}</Alert>}
    </div>
  );
}
