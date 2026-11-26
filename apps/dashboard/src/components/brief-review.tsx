"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Button, Field } from "@/components/ui";
import { api } from "@/lib/api-client";

/** Approve or reject one brief or render version. The API enforces which versions can be approved. */
export function ReviewForm({
  id,
  path,
  subject,
  approvable,
  blockedReason,
}: {
  id: string;
  path: string;
  subject: "brief" | "concept";
  approvable: boolean;
  blockedReason: string;
}) {
  const router = useRouter();
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function decide(approve: boolean) {
    if (!approve && !window.confirm(`Reject this ${subject} version?`)) return;
    setBusy(true);
    setError(null);
    const r = await api(path, "POST", { approve, notes });
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
          title={approvable ? undefined : blockedReason}
          onClick={() => decide(true)}
        >
          Approve {subject}
        </Button>
        <Button type="button" variant="danger" busy={busy} onClick={() => decide(false)}>
          Reject {subject}
        </Button>
      </div>
      {!approvable && <p className="text-xs text-muted">{blockedReason}</p>}
      {error && <Alert>{error}</Alert>}
    </div>
  );
}
