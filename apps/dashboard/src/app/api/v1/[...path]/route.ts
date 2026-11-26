import { connection, type NextRequest } from "next/server";

import { MAX_BODY_BYTES, buildForwardHeaders, copyResponseHeaders, isSafePath } from "@/lib/api-proxy";
import { getServerConfig } from "@/lib/server-config";

function errorResponse(status: number, code: string, message: string) {
  return Response.json(
    { code, message, correlation_id: null, field_errors: {} },
    { status, headers: { "cache-control": "no-store" } },
  );
}

async function forward(request: NextRequest, ctx: RouteContext<"/api/v1/[...path]">) {
  await connection();
  const { path } = await ctx.params;
  if (!isSafePath(path)) return errorResponse(404, "not_found", "Not found.");

  const config = getServerConfig();
  const target = new URL(`${config.apiInternalUrl}/api/v1/${path.join("/")}`);
  target.search = request.nextUrl.search;

  let body: ArrayBuffer | undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    const declared = Number(request.headers.get("content-length") ?? "0");
    if (declared > MAX_BODY_BYTES) return errorResponse(413, "payload_too_large", "Request is too large.");
    body = await request.arrayBuffer();
    if (body.byteLength > MAX_BODY_BYTES)
      return errorResponse(413, "payload_too_large", "Request is too large.");
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers: buildForwardHeaders(request.headers, config),
      body,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    return errorResponse(502, "api_unreachable", "The API is not reachable. Try again shortly.");
  }

  const headers = new Headers({ "cache-control": "no-store" });
  copyResponseHeaders(upstream.headers, headers);
  return new Response(upstream.status === 204 ? null : upstream.body, { status: upstream.status, headers });
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const PUT = forward;
export const DELETE = forward;
