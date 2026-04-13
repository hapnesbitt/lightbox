/**
 * Flask backend client for server-side use in Next.js.
 *
 * The Flask app at FLASK_INTERNAL_URL handles all business logic.
 * These helpers call Flask and parse the HTML responses into typed data.
 *
 * Design note: Flask returns HTML (Jinja2 templates). Where Flask embeds
 * JSON in script tags (slideshow endpoint) we parse that directly. For
 * pages that only render HTML, we use cheerio to extract data attributes
 * and class-annotated elements the Flask templates already emit.
 */

import { load } from 'cheerio';
import type { Batch, SlideshowItem, SessionUser } from './types';

const FLASK_URL = process.env.FLASK_INTERNAL_URL ?? 'http://localhost:5102';

// ---------------------------------------------------------------------------
// Low-level fetch helper
// ---------------------------------------------------------------------------

export async function callFlask(
  path: string,
  options: RequestInit & { cookieHeader?: string } = {}
): Promise<Response> {
  const { cookieHeader, ...rest } = options;
  const headers = new Headers(rest.headers as HeadersInit);
  if (cookieHeader) headers.set('Cookie', cookieHeader);

  return fetch(`${FLASK_URL}${path}`, {
    ...rest,
    headers,
    redirect: 'manual',   // never follow redirects — caller decides
    cache: 'no-store',
  });
}

// ---------------------------------------------------------------------------
// Parse helpers (all operate on Flask HTML)
// ---------------------------------------------------------------------------

/**
 * Extract the logged-in username from Flask's base.html navbar.
 * Flask renders: <a class="nav-link dropdown-toggle">...<i>...</i>USERNAME</a>
 */
export function parseUsername(html: string): string {
  const $ = load(html);
  const toggle = $('.nav-link.dropdown-toggle');
  // The anchor contains an <i> icon + the username as a text node
  toggle.find('i').remove();
  return toggle.text().trim();
}

/**
 * Extract batch list from Flask's index page.
 * Flask renders each batch as <div class="batch-card" data-batch-id="<uuid>">
 */
export function parseBatches(html: string): Batch[] {
  const $ = load(html);
  const batches: Batch[] = [];

  $('.batch-card').each((_, el) => {
    const id = $(el).attr('data-batch-id') ?? '';
    if (!id) return;

    const name = $(el).find('.batch-name-display').first().text().trim();
    const countText = $(el).find('.batch-item-count').first().text().trim();
    const itemCount = parseInt(countText, 10) || 0;

    batches.push({ id, name, itemCount });
  });

  return batches;
}

/**
 * Extract the CSRF token from any Flask page that renders a form.
 * Flask-WTF renders: <input name="csrf_token" value="TOKEN">
 */
export function parseCsrfToken(html: string): string {
  // Flask-WTF renders: <input id="csrf_token" name="csrf_token" type="hidden" value="TOKEN">
  // Attribute order varies — match the whole <input> tag regardless of order.
  const match =
    // name before value (most common)
    html.match(/<input[^>]+name=["']csrf_token["'][^>]+value=["']([^"']+)["']/) ??
    // value before name
    html.match(/<input[^>]+value=["']([^"']+)["'][^>]+name=["']csrf_token["']/);
  return match?.[1] ?? '';
}

/**
 * Extract the JSON media array embedded in Flask's slideshow page.
 * Flask renders: const mediaItems = [...];
 */
export function parseMediaItems(html: string): SlideshowItem[] {
  const match = html.match(/const\s+mediaItems\s*=\s*(\[[\s\S]*?\]);/);
  if (!match) return [];
  try {
    return JSON.parse(match[1]) as SlideshowItem[];
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// High-level data fetchers (used in Server Components)
// ---------------------------------------------------------------------------

/**
 * Check auth and return session user via Flask JSON endpoint.
 * Returns null if not authenticated (Flask would 302 → /login).
 */
export async function getSessionUser(cookieHeader: string): Promise<SessionUser | null> {
  const res = await callFlask('/api/me', { cookieHeader });
  if (res.status !== 200) return null;
  try {
    const data = await res.json() as { username?: string; is_admin?: boolean };
    if (!data.username) return null;
    return { username: data.username, isAdmin: data.is_admin };
  } catch {
    return null;
  }
}

/**
 * Fetch the batch list for the authenticated user via Flask JSON endpoint.
 * Falls back to HTML parsing for CSRF token (still needed for form submissions).
 */
export async function getBatches(cookieHeader: string): Promise<{
  batches: Batch[];
  csrfToken: string;
  username: string;
} | null> {
  // Fetch batch data from JSON endpoint + CSRF token from HTML in parallel
  const [jsonRes, htmlRes] = await Promise.all([
    callFlask('/api/batches', { cookieHeader }),
    callFlask('/', { cookieHeader }),
  ]);

  if (jsonRes.status !== 200) return null;

  try {
    const data = await jsonRes.json() as { batches: Batch[]; username: string };
    const html = htmlRes.status === 200 ? await htmlRes.text() : '';
    return {
      batches: data.batches ?? [],
      csrfToken: html ? parseCsrfToken(html) : '',
      username: data.username ?? '',
    };
  } catch {
    return null;
  }
}

/**
 * Fetch media items for a batch via Flask JSON endpoint.
 */
export async function getBatchDetail(
  batchId: string,
  cookieHeader: string
): Promise<{
  id: string;
  name: string;
  isShared: boolean;
  shareToken: string;
  publicUrl: string | null;
  media: import('./types').MediaItem[];
} | null> {
  const res = await callFlask(`/api/batch/${batchId}`, { cookieHeader });
  if (res.status !== 200) return null;
  try {
    return await res.json();
  } catch {
    return null;
  }
}

/**
 * Fetch public batch detail (no auth required).
 */
export async function getPublicBatch(shareToken: string): Promise<{
  id: string;
  name: string;
  shareToken: string;
  media: import('./types').MediaItem[];
} | null> {
  const res = await callFlask(`/api/batch/public/${shareToken}`);
  if (res.status !== 200) return null;
  try {
    return await res.json();
  } catch {
    return null;
  }
}

/**
 * Fetch slideshow items for a batch via Flask JSON endpoint.
 */
export async function getSlideshow(
  batchId: string,
  cookieHeader: string
): Promise<{ items: SlideshowItem[]; batchName: string } | null> {
  const res = await callFlask(`/api/slideshow/${batchId}`, { cookieHeader });
  if (res.status !== 200) return null;
  try {
    const data = await res.json() as { items: SlideshowItem[]; batchName: string };
    return data;
  } catch {
    return null;
  }
}

/**
 * Fetch public slideshow items (no auth required).
 */
export async function getPublicSlideshow(shareToken: string): Promise<{
  items: SlideshowItem[];
  batchName: string;
} | null> {
  const res = await callFlask(`/api/slideshow/public/${shareToken}`);
  if (res.status !== 200) return null;
  try {
    return await res.json();
  } catch {
    return null;
  }
}

/**
 * Get a CSRF token for form submissions.
 * Fetches Flask's main page and extracts the token.
 */
export async function getCsrfToken(cookieHeader: string): Promise<string> {
  const res = await callFlask('/', { cookieHeader });
  if (res.status !== 200) return '';
  const html = await res.text();
  return parseCsrfToken(html);
}

/**
 * Build the full static URL for a media file.
 * Flask stores filepath as "username/batch_id/file.mp4" (relative to static/uploads/).
 * Returns the public-facing URL usable from the browser.
 */
export function mediaUrl(filepath: string): string {
  // filepath is either already a full /static/... path (from slideshow JSON)
  // or a relative path from Redis
  if (filepath.startsWith('/')) return filepath;
  return `/static/uploads/${filepath}`;
}
