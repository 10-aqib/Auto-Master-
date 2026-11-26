import { NextResponse, type NextRequest } from "next/server";

import { refreshTokens } from "@/lib/api-proxy";
import { COOKIE } from "@/lib/auth-shared";
import { getServerConfig } from "@/lib/server-config";

const PUBLIC_PATHS = ["/login"];

function has(request: NextRequest, names: readonly string[]): boolean {
  return names.some((n) => request.cookies.has(n));
}

function parseSetCookie(value: string): { name: string; value: string } | null {
  const first = value.split(";", 1)[0];
  const eq = first.indexOf("=");
  return eq > 0 ? { name: first.slice(0, eq).trim(), value: first.slice(eq + 1).trim() } : null;
}

/**
 * Page requests only. When the short-lived access cookie has expired but a refresh cookie
 * exists, rotate tokens before rendering so server components see a valid session.
 */
export async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const isPublic = PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));

  if (has(request, COOKIE.access)) return NextResponse.next();

  if (has(request, COOKIE.refresh)) {
    const setCookies = await refreshTokens(
      request.headers.get("cookie") ?? "",
      request.headers,
      getServerConfig(),
    );
    if (setCookies) {
      // Make the new cookies visible to this render, and send them to the browser.
      for (const raw of setCookies) {
        const parsed = parseSetCookie(raw);
        if (parsed) request.cookies.set(parsed.name, parsed.value);
      }
      const response = NextResponse.next({ request: { headers: request.headers } });
      for (const raw of setCookies) response.headers.append("set-cookie", raw);
      return response;
    }
  }

  if (isPublic) return NextResponse.next();
  const login = new URL("/login", request.url);
  if (pathname !== "/") login.searchParams.set("next", pathname + search);
  return NextResponse.redirect(login);
}

export const config = {
  // Everything except API proxying, health, Next internals and static files.
  matcher: ["/((?!api/|health|_next/|favicon.ico).*)"],
};
