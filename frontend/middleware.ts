import { NextResponse, type NextRequest } from "next/server";

/**
 * Attaches the shared extension auth token to every /api/* request before Next's rewrite
 * (see next.config.mjs) proxies it to FastAPI.
 *
 * As of this session, the backend requires X-SimplyApply-Token on the routes it shares
 * with the browser extension (resumes/base, apply/{id} + cover-letter, download). Doing
 * this here — rather than in lib/api.ts — covers every caller in one place, including the
 * plain `<a href download>` tags in ApplyPanel/applications that hit /api/download/*
 * directly and can't set a custom header themselves; the header is added at this
 * server-side proxy hop instead.
 *
 * SIMPLYAPPLY_EXTENSION_TOKEN must be set to the same value the backend generated (logged
 * once at backend startup, or pinned via the same env var on both services). Requests
 * still reach the backend without it; the backend just answers 401 for the routes that
 * need it.
 */
export function middleware(request: NextRequest) {
  const token = process.env.SIMPLYAPPLY_EXTENSION_TOKEN;
  if (!token) return NextResponse.next();

  const headers = new Headers(request.headers);
  headers.set("X-SimplyApply-Token", token);
  return NextResponse.next({ request: { headers } });
}

export const config = {
  matcher: "/api/:path*",
};
