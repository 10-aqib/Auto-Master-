import { cookies } from "next/headers";
import { connection, type NextRequest } from "next/server";

import { getServerConfig } from "@/lib/server-config";

const SAFE_ID = /^[0-9a-f-]{36}$/;

/** Downloads a proposal PDF from the API with the viewer's session (never public). */
export async function GET(_req: NextRequest, ctx: RouteContext<"/api/proposal-pdf/[proposal]">) {
  await connection();
  const { proposal } = await ctx.params;
  if (!SAFE_ID.test(proposal)) return new Response("Not found", { status: 404 });
  const config = getServerConfig();
  const upstream = await fetch(`${config.apiInternalUrl}/api/v1/proposals/${proposal}/pdf`, {
    headers: { cookie: (await cookies()).toString() },
    cache: "no-store",
  }).catch(() => null);
  if (!upstream || !upstream.ok)
    return new Response("Not found", { status: upstream?.status === 401 ? 401 : 404 });
  return new Response(upstream.body, {
    headers: {
      "content-type": "application/pdf",
      "content-disposition": upstream.headers.get("content-disposition") ?? "attachment",
      "cache-control": "private, no-store",
      "x-content-type-options": "nosniff",
    },
  });
}
