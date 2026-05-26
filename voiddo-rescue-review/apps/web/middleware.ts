import { NextRequest, NextResponse } from "next/server";

function tokenFromBasic(header: string) {
  if (!header.toLowerCase().startsWith("basic ")) return "";
  try {
    const decoded = atob(header.slice(6));
    return decoded.split(":").slice(1).join(":");
  } catch {
    return "";
  }
}

export function middleware(request: NextRequest) {
  const expected = process.env.ADMIN_AUTH_TOKEN || "";
  if (!request.nextUrl.pathname.startsWith("/admin")) {
    return NextResponse.next();
  }
  if (!expected) {
    return new NextResponse("admin auth token not configured", { status: 503 });
  }
  const authorization = request.headers.get("authorization") || "";
  const bearer = authorization.toLowerCase().startsWith("bearer ") ? authorization.slice(7).trim() : "";
  const basic = tokenFromBasic(authorization);
  if (bearer === expected || basic === expected) {
    return NextResponse.next();
  }
  return new NextResponse("admin auth required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Vøiddo Rescue Admin"' },
  });
}

export const config = {
  matcher: ["/admin/:path*"],
};
