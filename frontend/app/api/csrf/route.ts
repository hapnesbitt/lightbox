import { type NextRequest, NextResponse } from 'next/server';
import { callFlask } from '@/lib/flask';

export async function GET(request: NextRequest) {
  const cookieHeader = request.headers.get('cookie') ?? '';
  const res = await callFlask('/api/csrf-token', { cookieHeader });
  const rawBody = await res.text();
  console.log('[csrf] Flask status:', res.status, 'body:', rawBody.slice(0, 500));
  if (!res.ok) {
    return NextResponse.json({ error: 'Could not fetch CSRF token from Flask' }, { status: 502 });
  }
  let csrf_token: string | undefined;
  try {
    ({ csrf_token } = JSON.parse(rawBody));
  } catch {
    console.log('[csrf] JSON parse error, raw body:', rawBody.slice(0, 500));
    return NextResponse.json({ error: 'Flask returned non-JSON response' }, { status: 502 });
  }
  if (!csrf_token) {
    return NextResponse.json({ error: 'Flask returned no CSRF token' }, { status: 502 });
  }
  return NextResponse.json({ csrfToken: csrf_token });
}
