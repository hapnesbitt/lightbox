import { NextRequest, NextResponse } from 'next/server';

// Paths that don't require authentication
const PUBLIC_PATHS = [
  '/login',
  '/register',
  '/public',
  '/about',
  '/why-lightbox',
  '/ross-nesbitt',
];

// Next.js internal paths — never intercept
const SKIP_PREFIXES = ['/_next', '/api', '/icons', '/manifest.json', '/sw.js', '/favicon'];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Skip Next.js internals and static assets
  if (SKIP_PREFIXES.some((p) => pathname.startsWith(p))) return NextResponse.next();

  // Skip public routes
  if (PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p + '/'))) {
    return NextResponse.next();
  }

  // Check for Flask session cookie (default name is 'session')
  const sessionCookie = request.cookies.get('session');
  if (!sessionCookie?.value) {
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set('next', pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all paths except:
     * - _next/static (Next.js static files)
     * - _next/image (image optimization)
     * - favicon.ico
     */
    '/((?!_next/static|_next/image|favicon\\.ico).*)',
  ],
};
