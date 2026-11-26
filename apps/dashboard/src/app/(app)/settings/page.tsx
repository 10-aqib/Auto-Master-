import { ControlToggle } from "@/components/control-toggle";
import { Alert } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import type { Control } from "@/lib/discovery";

export const metadata = { title: "Settings · WEBFORGE AI" };

export default async function SettingsPage() {
  const { user } = await requireActiveSession(["OWNER", "ADMIN"]);
  const controls = await apiServer<Control[]>("/controls");
  return (
    <div className="grid gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-2 text-sm text-muted">
          Pause switches take effect immediately. Admins can pause; only the owner can resume.
        </p>
      </header>
      {controls.ok ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {controls.data.map((c) => (
            <ControlToggle key={c.key} control={c} role={user.role} />
          ))}
        </div>
      ) : (
        <Alert>{controls.error.message}</Alert>
      )}
    </div>
  );
}
