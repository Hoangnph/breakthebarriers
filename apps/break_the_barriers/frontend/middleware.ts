import { NextRequest, NextResponse } from "next/server"

const PROTECTED = ["/dashboard", "/books"]

export function middleware(request: NextRequest) {
  const token = request.cookies.get("btb_token")
  const { pathname } = request.nextUrl

  const isProtected = PROTECTED.some((p) => pathname.startsWith(p))
  if (isProtected && !token) {
    return NextResponse.redirect(new URL("/login", request.url))
  }
  return NextResponse.next()
}

export const config = {
  matcher: ["/dashboard/:path*", "/books/:path*"],
}
