"use client";

import { useState, type FormEvent } from "react";

import { VerificationResult } from "@/components/verification-result";
import { Alert, Button, Field } from "@/components/ui";
import { api } from "@/lib/api-client";
import type { VerifyResponse } from "@/lib/sources";

export function OwnerVerifyForm({ enabled }: { enabled: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VerifyResponse | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    setResult(null);
    const r = await api<VerifyResponse>("/verification/website", "POST", {
      url: String(form.get("url") ?? ""),
      expected_name: String(form.get("expected_name") ?? ""),
    });
    setBusy(false);
    if (r.ok) setResult(r.data);
    else setError(r.error.message);
  }

  return (
    <form onSubmit={onSubmit} className="grid gap-4 sm:grid-cols-2" noValidate>
      {!enabled && (
        <div className="sm:col-span-2">
          <Alert tone="info">Enable “Business-owned official websites” above to use this check.</Alert>
        </div>
      )}
      <Field
        id="verify-url"
        name="url"
        type="url"
        label="Website you already know"
        placeholder="https://"
        required
      />
      <Field id="verify-name" name="expected_name" label="Business name you expect" required />
      <div className="sm:col-span-2 grid gap-3">
        <Button type="submit" busy={busy} disabled={!enabled} className="justify-self-start">
          Verify website
        </Button>
        {error && <Alert>{error}</Alert>}
        {result && <VerificationResult v={result.verification} prospectId={result.prospect_id} />}
      </div>
    </form>
  );
}
