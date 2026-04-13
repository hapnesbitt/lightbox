/**
 * Transparent catch-all proxy to the Flask backend.
 *
 * All Flask routes (login, upload, toggle, delete, batch ops, etc.) are
 * forwarded here so the browser only ever talks to the Next.js origin.
 * Session cookies are forwarded in both directions.
 *
 * Usage from client code:
 *   fetch('/api/flask/login', { method: 'POST', body: formData })
 *   fetch('/api/flask/upload',  { method: 'POST', body: formData })
 */

import { type NextRequest, NextResponse } from 'next/server';

const FLASK_URL = process.env.FLASK_INTERNAL_URL ?? 'http://localhost:5102';

// Headers we must not forward upstream (Next.js internals + Flask-WTF referrer check)
const HOP_BY_HOP = new Set([
  'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
  'te', 'trailers', 'transfer-encoding', 'upgrade',
  'host',                  // rewritten to Flask host
  'referer',               // rewritten to production host below; strip original so it doesn't bleed through
]);

async function handler(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const flaskPath = '/' + path.join('/');
  const search = request.nextUrl.search;
  const targetUrl = `${FLASK_URL}${flaskPath}${search}`;

  // Build forwarded headers
  const headers = new Headers();
  for (const [key, value] of request.headers.entries()) {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  }
  // Rewrite Origin and Referer to the production host so Flask-WTF's CSRF
  // origin and referrer checks pass against WTF_CSRF_TRUSTED_ORIGINS.
  headers.set('origin', 'https://vid.arc-codex.com');
  headers.set('referer', 'https://vid.arc-codex.com/');

  // Debug: log cookie presence for every proxied request
  const cookieHeader = request.headers.get('cookie') ?? '';
  const hasSession = cookieHeader.includes('session=');
  console.log(
    `[flask-proxy] ${request.method} ${flaskPath} | cookie: ${cookieHeader ? `${cookieHeader.length}b` : 'NONE'} | session: ${hasSession}`
  );

  let body: BodyInit | null = null;
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    body = await request.arrayBuffer();
  }

  console.log('[flask-proxy] sending referer:', headers.get('referer'), 'origin:', headers.get('origin'));

  let flaskResponse: Response;
  try {
    flaskResponse = await fetch(targetUrl, {
      method: request.method,
      headers,
      body,
      redirect: 'manual',
      // @ts-expect-error — Node 18+ fetch supports duplex
      duplex: 'half',
    });
  } catch (err) {
    console.error('[flask-proxy] fetch error:', err);
    return NextResponse.json({ error: 'Flask backend unreachable' }, { status: 502 });
  }

  console.log(`[flask-proxy] Flask → ${flaskResponse.status} ${flaskPath}`);

  // Build response — copy status, headers, body
  const responseHeaders = new Headers();
  for (const [key, value] of flaskResponse.headers.entries()) {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      responseHeaders.append(key, value);
    }
  }

  // Flask may redirect to /login or /collection/<id> after upload.
  // Flask's url_for() generates absolute URLs with the internal host
  // (e.g. http://localhost:5102/login) — we must strip the host before
  // returning, otherwise the browser follows a cross-origin redirect and
  // CORS kills the request.
  //
  // For XHR / JSON requests: convert redirect to { redirect: "/path" } JSON.
  // For plain requests: pass the 302 through with a corrected Location header.
  const isXhr = request.headers.get('x-requested-with') === 'XMLHttpRequest'
    || request.headers.get('accept')?.includes('application/json')
    || flaskPath === '/upload';

  if (flaskResponse.status === 301 || flaskResponse.status === 302) {
    const rawLocation = flaskResponse.headers.get('location') ?? '/';
    // Strip internal host — make location relative so browser stays same-origin
    // Rewrite /collection/<uuid> → /batch/<uuid> (Flask route → Next.js route)
    let location = rawLocation.replace(/^https?:\/\/[^/]+/, '');
    location = location.replace('/collection/', '/batch/');

    if (isXhr) {
      return NextResponse.json({ redirect: location }, { status: 200, headers: responseHeaders });
    }

    responseHeaders.set('location', location);
    return new NextResponse(null, {
      status: flaskResponse.status,
      statusText: flaskResponse.statusText,
      headers: responseHeaders,
    });
  }

  const responseBody = await flaskResponse.arrayBuffer();

  // Log unexpected non-2xx responses so we can debug without guessing
  if (flaskResponse.status >= 400) {
    const bodyText = new TextDecoder().decode(responseBody).slice(0, 500);
    console.error(
      `[flask-proxy] ERROR ${flaskResponse.status} on ${request.method} ${flaskPath}\n` +
      `  cookie forwarded: ${hasSession}\n` +
      `  body snippet: ${bodyText}`
    );
  }

  return new NextResponse(responseBody, {
    status: flaskResponse.status,
    statusText: flaskResponse.statusText,
    headers: responseHeaders,
  });
}

export const GET    = handler;
export const POST   = handler;
export const PUT    = handler;
export const PATCH  = handler;
export const DELETE = handler;
export const HEAD   = handler;
export const OPTIONS = handler;
