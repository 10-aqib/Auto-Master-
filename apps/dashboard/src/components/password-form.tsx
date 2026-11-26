"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Alert, Button, Field } from "@/components/ui";
import { api } from "@/lib/api-client";
import { pathForState, type AuthResponse } from "@/lib/auth-shared";

export function PasswordForm({ doneHref }: { doneHref?: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [done, setDone] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const next = String(form.get("new_password") ?? "");
    if (next !== String(form.get("confirm") ?? "")) {
      setFieldErrors({ confirm: "Passwords do not match." });
      return;
    }
    setBusy(true);
    setError(null);
    setFieldErrors({});
    const result = await api<AuthResponse>("/auth/password", "POST", {
      current_password: String(form.get("current_password") ?? ""),
      new_password: next,
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.error.message);
      setFieldErrors(result.error.field_errors);
      return;
    }
    formEl.reset();
    if (doneHref) {
      router.replace(pathForState(result.data.session.state) ?? doneHref);
      router.refresh();
    } else {
      setDone(true);
    }
  }

  return (
    <form onSubmit={onSubmit} className="grid gap-4" noValidate>
      {error && <Alert>{error}</Alert>}
      {done && <Alert tone="success">Password changed. Other sessions were signed out.</Alert>}
      <Field
        id="current_password"
        name="current_password"
        type="password"
        label="Current password"
        autoComplete="current-password"
        required
      />
      <Field
        id="new_password"
        name="new_password"
        type="password"
        label="New password"
        autoComplete="new-password"
        hint="At least 12 characters. A passphrase of several words works well."
        error={fieldErrors.new_password}
        minLength={12}
        required
      />
      <Field
        id="confirm"
        name="confirm"
        type="password"
        label="Confirm new password"
        autoComplete="new-password"
        error={fieldErrors.confirm}
        required
      />
      <Button type="submit" busy={busy}>
        Change password
      </Button>
    </form>
  );
}
