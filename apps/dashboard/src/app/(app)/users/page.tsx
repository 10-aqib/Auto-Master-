import { UsersManager } from "@/components/users-manager";
import { Alert } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import type { User } from "@/lib/auth-shared";

export const metadata = { title: "Users · WEBFORGE AI" };

export default async function UsersPage() {
  const { user } = await requireActiveSession(["OWNER", "ADMIN"]);
  const users = await apiServer<User[]>("/users");
  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
      {users.ok ? <UsersManager users={users.data} actor={user} /> : <Alert>{users.error.message}</Alert>}
    </div>
  );
}
