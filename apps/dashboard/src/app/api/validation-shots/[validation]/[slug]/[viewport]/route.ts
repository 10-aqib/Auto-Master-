import { cookies } from "next/headers";
import { connection, type NextRequest } from "next/server";

import { PAGE_SLUGS, VIEWPORTS } from "@/lib/designs";
import { getServerConfig } from "@/lib/server-config";

const SAFE_ID = /^[0-9a-f-]{36}$/;

/** Streams a validation screenshot from the API using the viewer's session (never public). */
export async function GET(
  _req: NextRequest,
  ctx: RouteContext<"/api/validation-shots/[validation]/[slug]/[viewport]">,
) {
  await connection();
  const { validation, slug, viewport } = await ctx.params;
  if (
    !SAFE_ID.test(validation) ||
    !(PAGE_SLUGS as readonly string[]).includes(slug) ||
    !(VIEWPORTS as readonly string[]).includes(viewport)
  )
    return new Response("Not found", { status: 404 });
  const config = getServerConfig();
  const upstream = await fetch(
    `${config.apiInternalUrl}/api/v1/designs/validations/${validation}/screenshots/${slug}/${viewport}`,
    { headers: { cookie: (await cookies()).toString() }, cache: "no-store" },
  ).catch(() => null);
  if (!upstream || !upstream.ok)
    return new Response("Not found", { status: upstream?.status === 401 ? 401 : 404 });
  return new Response(upstream.body, {
    headers: {
      "content-type": "image/png",
      "cache-control": "private, no-store",
      "x-content-type-options": "nosniff",
    },
  });
}
