"use client";

import { COOKIE, isApiErrorBody, type ApiErrorBody } from "@/lib/auth-shared";

export type ApiResult<T> =
  { ok: true; status: number; data: T } | { ok: false; status: number; error: ApiErrorBody };

function readCookie(names: readonly string[]): string | undefined {
  const jar = new Map(
    document.cookie
      .split(";")
      .map((part) => part.trim().split("="))
      .filter((kv) => kv.length >= 2)
      .map(([k, ...v]) => [k, decodeURIComponent(v.join("="))] as const),
  );
  for (const name of names) {
    const value = jar.get(name);
    if (value) return value;
  }
  return undefined;
}

async function send(path: string, init: { method: string; body?: unknown }): Promise<Response> {
  const headers: Record<string, string> = { accept: "application/json" };
  if (init.body !== undefined) headers["content-type"] = "application/json";
  const csrf = readCookie(COOKIE.csrf);
  if (csrf && init.method !== "GET") headers["x-csrf-token"] = csrf;
  return fetch(`/api/v1${path}`, {
    method: init.method,
    headers,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    credentials: "same-origin",
    cache: "no-store",
  });
}

async function parse<T>(response: Response): Promise<ApiResult<T>> {
  if (response.status === 204) return { ok: true, status: 204, data: undefined as T };
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (response.ok) return { ok: true, status: response.status, data: body as T };
  const error: ApiErrorBody = isApiErrorBody(body)
    ? { ...body, field_errors: body.field_errors ?? {} }
    : {
        code: "unexpected_response",
        message: `Request failed (HTTP ${response.status}).`,
        correlation_id: null,
        field_errors: {},
      };
  return { ok: false, status: response.status, error };
}

/** Browser → dashboard proxy → API. Refreshes once on an expired access token. */
export async function api<T>(path: string, method = "GET", body?: unknown): Promise<ApiResult<T>> {
  let result = await parse<T>(await send(path, { method, body }));
  if (
    !result.ok &&
    result.status === 401 &&
    ["token_expired", "not_authenticated"].includes(result.error.code)
  ) {
    const refreshed = await send("/auth/refresh", { method: "POST" });
    if (refreshed.ok) result = await parse<T>(await send(path, { method, body }));
  }
  return result;
}
