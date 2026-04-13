import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const FLASK_URL = process.env.FLASK_INTERNAL_URL ?? 'http://localhost:5102';

export async function GET() {
  // Forward the session cookie so Flask can invalidate the server-side session.
  const cookieStore = await cookies();
  const cookieHeader = cookieStore.toString();

  try {
    await fetch(`${FLASK_URL}/logout`, {
      method: 'GET',
      headers: cookieHeader ? { cookie: cookieHeader } : {},
      redirect: 'manual',
      cache: 'no-store',
    });
  } catch {
    // Flask unreachable — still clear the cookie and redirect.
  }

  const response = NextResponse.redirect('https://vid.arc-codex.com/login');
  response.cookies.set('session', '', { maxAge: 0, path: '/' });
  return response;
}
