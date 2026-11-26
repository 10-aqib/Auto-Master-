import { cookies } from "next/headers";
import { connection, type NextRequest } from "next/server";

import { CONCEPT_CSP, PAGE_SLUGS } from "@/lib/designs";
import { getServerConfig } from "@/lib/server-config";

const SAFE_ID = /^[0-9a-f-]{36}$/;

/** Streams one rendered concept page from the API for signed-in staff, sandboxed (no scripts, no forms). */
export async function GET(_req: NextRequest, ctx: RouteContext<"/api/concepts/[render]/[slug]">) {
  await connection();
  const { render, slug } = await ctx.params;
  if (!SAFE_ID.test(render) || !(PAGE_SLUGS as readonly string[]).includes(slug))
    return new Response("Not found", { status: 404 });
  const config = getServerConfig();
  const upstream = await fetch(`${config.apiInternalUrl}/api/v1/designs/renders/${render}/pages/${slug}`, {
    headers: { cookie: (await cookies()).toString() },
    cache: "no-store",
  }).catch(() => null);
  if (!upstream || !upstream.ok)
    return new Response("Not found", { status: upstream?.status === 401 ? 401 : 404 });
  return new Response(upstream.body, {
    headers: {
      "content-type": "text/html; charset=utf-8",
      "content-security-policy": CONCEPT_CSP,
      "x-frame-options": "SAMEORIGIN",
      "cache-control": "private, no-store",
      "x-content-type-options": "nosniff",
      "referrer-policy": "no-referrer",
    },
  });
}
