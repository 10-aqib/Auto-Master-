"use client";

import { useState } from "react";

import { Alert, Button, formatDate } from "@/components/ui";
import { api } from "@/lib/api-client";

export interface ActivityItem {
  id: string;
  occurred_at: string;
  actor_user_id: string | null;
  actor_type: string;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  outcome: "success" | "failure" | "denied";
  request_id: string | null;
  metadata: Record<string, unknown>;
}

export interface ActivityPage {
  items: ActivityItem[];
  next_cursor: string | null;
}

const OUTCOME_TONE: Record<ActivityItem["outcome"], string> = {
  success: "text-emerald-700 dark:text-emerald-300",
  failure: "text-amber-700 dark:text-amber-300",
  denied: "text-rose-700 dark:text-rose-300",
};

export function ActivityTable({
  initial,
  actors,
}: {
  initial: ActivityPage;
  actors: Record<string, string>;
}) {
  const [items, setItems] = useState(initial.items);
  const [cursor, setCursor] = useState(initial.next_cursor);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadMore() {
    if (!cursor) return;
    setBusy(true);
    const r = await api<ActivityPage>(`/activity?limit=50&cursor=${encodeURIComponent(cursor)}`);
    setBusy(false);
    if (!r.ok) return setError(r.error.message);
    setItems((prev) => [...prev, ...r.data.items]);
    setCursor(r.data.next_cursor);
  }

  return (
    <div className="grid gap-4">
      {error && <Alert>{error}</Alert>}
      <div className="overflow-x-auto rounded-xl border border-line bg-surface">
        <table className="w-full min-w-[40rem] text-sm">
          <caption className="sr-only">Activity log, newest first</caption>
          <thead className="text-left text-muted">
            <tr>
              <th scope="col" className="px-4 py-3 font-medium">
                When
              </th>
              <th scope="col" className="px-4 py-3 font-medium">
                Action
              </th>
              <th scope="col" className="px-4 py-3 font-medium">
                Actor
              </th>
              <th scope="col" className="px-4 py-3 font-medium">
                Outcome
              </th>
              <th scope="col" className="px-4 py-3 font-medium">
                Details
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} className="border-t border-line align-top">
                <td className="whitespace-nowrap px-4 py-3 tabular-nums">{formatDate(item.occurred_at)}</td>
                <td className="px-4 py-3 font-mono text-xs">{item.action}</td>
                <td className="px-4 py-3">
                  {item.actor_user_id ? (actors[item.actor_user_id] ?? "Unknown user") : item.actor_type}
                </td>
                <td className={`px-4 py-3 font-medium capitalize ${OUTCOME_TONE[item.outcome]}`}>
                  {item.outcome}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-muted">
                  {Object.keys(item.metadata).length ? JSON.stringify(item.metadata) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {cursor && (
        <Button
          type="button"
          variant="secondary"
          busy={busy}
          onClick={loadMore}
          className="justify-self-start"
        >
          Load older entries
        </Button>
      )}
    </div>
  );
}
