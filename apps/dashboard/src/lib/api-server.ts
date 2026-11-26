/** Server components: call the API with the visitor's cookies. */

import { cookies, headers } from "next/headers";
import { cache } from "react";
import { redirect } from "next/navigation";

import { buildForwardHeaders } from "@/lib/api-proxy";
import {
  isApiErrorBody,
  pathForState,
  type ApiErrorBody,
  type MeResponse,
  type Role,
} from "@/lib/auth-shared";
import { getServerConfig } from "@/lib/server-config";

export type ServerResult<T> = { ok: true; data: T } | { ok: false; status: number; error: ApiErrorBody };

export async function apiServer<T>(path: string): Promise<ServerResult<T>> {
  const config = getServerConfig();
  const forward = buildForwardHeaders(await headers(), config);
  forward.set("cookie", (await cookies()).toString());
  forward.set("accept", "application/json");
  let response: Response;
  try {
    response = await fetch(`${config.apiInternalUrl}/api/v1${path}`, {
      headers: forward,
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
  } catch {
    return {
      ok: false,
      status: 502,
      error: {
        code: "api_unreachable",
        message: "The API is not reachable.",
        correlation_id: null,
        field_errors: {},
      },
    };
  }
  const body: unknown = await response.json().catch(() => null);
  if (response.ok) return { ok: true, data: body as T };
  return {
    ok: false,
    status: response.status,
    error: isApiErrorBody(body)
      ? body
      : {
          code: "unexpected_response",
          message: `HTTP ${response.status}`,
          correlation_id: null,
          field_errors: {},
        },
  };
}

/** One /auth/me call per request, shared by the layout and the page. */
const getMe = cache(() => apiServer<MeResponse>("/auth/me"));

/** Current user with an ACTIVE session, or a redirect to the step the session needs. */
export async function requireActiveSession(roles?: Role[]): Promise<MeResponse> {
  const me = await getMe();
  if (!me.ok) {
    if (me.status === 401) redirect("/login");
    throw new Error(`Could not load session: ${me.error.code}`);
  }
  const next = pathForState(me.data.session.state);
  if (next) redirect(next);
  if (roles && !roles.includes(me.data.user.role)) redirect("/");
  return me.data;
}

/** Session in any state (used by the login/setup steps). Null when signed out. */
export async function currentSession(): Promise<MeResponse | null> {
  const me = await getMe();
  return me.ok ? me.data : null;
}
