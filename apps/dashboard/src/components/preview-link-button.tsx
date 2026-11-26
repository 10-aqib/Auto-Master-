"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Button } from "@/components/ui";
import { api } from "@/lib/api-client";

/** Creates a preview link and shows it once: only a hash of the token is stored by the API. */
export function PreviewLinkButton({ proposalId }: { proposalId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function create() {
    setBusy(true);
    setError(null);
    const r = await api<{ url: string }>(`/proposals/${proposalId}/previews`, "POST", {});
    setBusy(false);
    if (!r.ok) return setError(r.error.message);
    setUrl(r.data.url);
    router.refresh();
  }

  return (
    <div className="grid gap-2">
      <div>
        <Button type="button" variant="secondary" busy={busy} onClick={create}>
          Create preview link
        </Button>
      </div>
      {url && (
        <div className="grid gap-1 rounded-lg border border-line p-3 text-sm" role="status">
          <span className="font-medium">New preview link (shown once; copy it now)</span>
          <code data-testid="preview-url" className="break-all">
            {url}
          </code>
          <div>
            <Button
              type="button"
              variant="secondary"
              onClick={async () => {
                await navigator.clipboard?.writeText(url).catch(() => undefined);
                setCopied(true);
              }}
            >
              {copied ? "Copied" : "Copy link"}
            </Button>
          </div>
        </div>
      )}
      {error && <Alert>{error}</Alert>}
    </div>
  );
}
