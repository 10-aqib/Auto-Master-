"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";

import { Alert, Button } from "@/components/ui";
import { api } from "@/lib/api-client";

/**
 * A small form that turns its named fields into a JSON body, posts it, shows API errors (including
 * per-field errors) and refreshes the page. `transform` adjusts the body before sending.
 */
export function JsonForm({
  path,
  method = "POST",
  submitLabel,
  children,
  transform,
  className = "grid gap-3",
  confirmText,
  onDone,
  pathFrom,
}: {
  path: string;
  pathFrom?: (body: Record<string, string>) => string;
  method?: string;
  submitLabel: string;
  children: ReactNode;
  transform?: (body: Record<string, string>) => unknown;
  className?: string;
  confirmText?: string;
  onDone?: (data: unknown) => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    if (confirmText && !window.confirm(confirmText)) return;
    const form = new FormData(formEl);
    const raw: Record<string, string> = {};
    for (const [k, v] of form.entries()) raw[k] = String(v);
    let body: unknown;
    let target = path;
    try {
      body = transform ? transform(raw) : raw;
      if (pathFrom) target = pathFrom(raw);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid input.");
      return;
    }
    setBusy(true);
    setError(null);
    const r = await api(target, method, body);
    setBusy(false);
    if (!r.ok) {
      const fields = Object.entries(r.error.field_errors ?? {})
        .map(([k, v]) => `${k}: ${v}`)
        .join("; ");
      return setError(fields ? `${r.error.message} (${fields})` : r.error.message);
    }
    formEl.reset();
    onDone?.(r.data);
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className={className} noValidate>
      {children}
      <div>
        <Button type="submit" busy={busy}>
          {submitLabel}
        </Button>
      </div>
      {error && <Alert>{error}</Alert>}
    </form>
  );
}

export function Select({
  label,
  name,
  options,
  defaultValue,
}: {
  label: string;
  name: string;
  options: { value: string; label: string }[];
  defaultValue?: string;
}) {
  return (
    <label className="grid gap-1.5 text-sm font-medium">
      {label}
      <select
        name={name}
        defaultValue={defaultValue}
        className="min-h-10 rounded-lg border border-line bg-background px-3 font-normal"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function TextArea({
  label,
  name,
  rows = 4,
  defaultValue,
  hint,
}: {
  label: string;
  name: string;
  rows?: number;
  defaultValue?: string;
  hint?: string;
}) {
  return (
    <label className="grid gap-1.5 text-sm font-medium">
      {label}
      <textarea
        name={name}
        rows={rows}
        defaultValue={defaultValue}
        className="rounded-lg border border-line bg-background px-3 py-2 font-mono text-xs font-normal"
      />
      {hint && <span className="text-xs font-normal text-muted">{hint}</span>}
    </label>
  );
}
