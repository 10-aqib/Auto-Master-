"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Button } from "@/components/ui";
import { api } from "@/lib/api-client";

/** A button that calls one API endpoint, shows errors, and refreshes the page on success. */
export function ActionButton({
  path,
  method = "POST",
  body,
  label,
  variant = "secondary",
  confirmText,
  disabledReason,
  onDone,
}: {
  path: string;
  method?: string;
  body?: unknown;
  label: string;
  variant?: "primary" | "secondary" | "danger";
  confirmText?: string;
  disabledReason?: string;
  onDone?: (data: unknown) => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <span className="inline-grid gap-1">
      <Button
        type="button"
        variant={variant}
        busy={busy}
        disabled={Boolean(disabledReason)}
        title={disabledReason}
        onClick={async () => {
          if (confirmText && !window.confirm(confirmText)) return;
          setBusy(true);
          setError(null);
          const r = await api(path, method, body ?? (method === "GET" ? undefined : {}));
          setBusy(false);
          if (!r.ok) return setError(r.error.message);
          onDone?.(r.data);
          router.refresh();
        }}
      >
        {label}
      </Button>
      {disabledReason && <span className="text-xs text-muted">{disabledReason}</span>}
      {error && <Alert>{error}</Alert>}
    </span>
  );
}
