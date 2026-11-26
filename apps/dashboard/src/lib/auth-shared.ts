/** Shared between server, proxy and browser code. No secrets here. */

export const COOKIE = {
  access: ["__Host-wf_at", "wf_at"],
  refresh: ["__Host-wf_rt", "wf_rt"],
  csrf: ["__Host-wf_csrf", "wf_csrf"],
} as const;

export type SessionState = "mfa_pending" | "mfa_enrollment_required" | "password_change_required" | "active";
export type Role = "OWNER" | "ADMIN" | "REVIEWER" | "READ_ONLY";

export const ROLE_LABEL: Record<Role, string> = {
  OWNER: "Owner",
  ADMIN: "Admin",
  REVIEWER: "Reviewer",
  READ_ONLY: "Read-only",
};

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: Role;
  is_active: boolean;
  mfa_enabled: boolean;
  password_change_required: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface SessionStatus {
  state: SessionState;
  session_id: string;
  access_expires_at?: string | null;
  recovery_codes_remaining?: number | null;
}

export interface AuthResponse {
  user: User;
  session: SessionStatus;
  csrf_token: string;
}

export interface MeResponse {
  user: User;
  session: SessionStatus;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  correlation_id: string | null;
  field_errors: Record<string, string>;
}

/** Where a session in `state` must go next. */
export function pathForState(state: SessionState): string | null {
  switch (state) {
    case "mfa_pending":
      return "/login/mfa";
    case "mfa_enrollment_required":
      return "/setup/mfa";
    case "password_change_required":
      return "/setup/password";
    default:
      return null;
  }
}

/** Only allow same-site relative redirects (no open redirect via ?next=). */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return "/";
  if (next.startsWith("/login") || next.startsWith("/setup")) return "/";
  return next;
}

export function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.code === "string" && typeof v.message === "string";
}
