import { ActivityTable, type ActivityPage } from "@/components/activity-table";
import { Alert } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import type { User } from "@/lib/auth-shared";

export const metadata = { title: "Activity · WEBFORGE AI" };

export default async function ActivityPageView() {
  await requireActiveSession(["OWNER", "ADMIN"]);
  const [page, users] = await Promise.all([
    apiServer<ActivityPage>("/activity?limit=50"),
    apiServer<User[]>("/users"),
  ]);
  const actors = users.ok ? Object.fromEntries(users.data.map((u) => [u.id, u.display_name])) : {};
  return (
    <div className="grid gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Activity</h1>
        <p className="mt-2 text-sm text-muted">
          Append-only record of sign-ins and privileged actions. Entries cannot be edited or deleted.
        </p>
      </header>
      {page.ok ? <ActivityTable initial={page.data} actors={actors} /> : <Alert>{page.error.message}</Alert>}
    </div>
  );
}
