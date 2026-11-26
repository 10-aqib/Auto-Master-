"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui";
import { api } from "@/lib/api-client";

export function SignOutButton({ everywhere = false }: { everywhere?: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  return (
    <Button
      type="button"
      variant={everywhere ? "danger" : "secondary"}
      busy={busy}
      onClick={async () => {
        setBusy(true);
        await api(everywhere ? "/auth/logout-all" : "/auth/logout", "POST");
        router.replace("/login");
        router.refresh();
      }}
    >
      {everywhere ? "Sign out of all sessions" : "Sign out"}
    </Button>
  );
}
