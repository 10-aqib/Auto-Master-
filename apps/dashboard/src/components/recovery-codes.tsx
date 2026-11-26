"use client";

import { useState } from "react";

import { Alert, Button } from "@/components/ui";

export function RecoveryCodes({ codes }: { codes: string[] }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="grid gap-3">
      <Alert tone="info">
        Save these recovery codes somewhere safe, such as a password manager. Each works once. They will not
        be shown again.
      </Alert>
      <ul
        className="grid grid-cols-2 gap-2 rounded-lg bg-background p-3 font-mono text-sm"
        aria-label="Recovery codes"
      >
        {codes.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
      <Button
        type="button"
        variant="secondary"
        onClick={async () => {
          await navigator.clipboard.writeText(codes.join("\n"));
          setCopied(true);
        }}
      >
        {copied ? "Copied" : "Copy codes"}
      </Button>
    </div>
  );
}
