# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**LightBox** — a Next.js 15 frontend for a personal media library, served on port 3005. It is a pure UI layer that delegates all business logic to a Flask backend running natively on port 5102. The two processes are never in the same container: Next.js runs in Docker (host networking), Flask runs on the host.

Production site: `vid.arc-codex.com`

## Stack management

```bash
./claude_vid.sh start      # start Docker container
./claude_vid.sh stop       # stop container
./claude_vid.sh restart    # stop + start
./claude_vid.sh build      # rebuild image (no-cache) then start
./claude_vid.sh status     # show container + port state
./claude_vid.sh logs       # tail Docker logs
./claude_vid.sh checkup    # full health check (image, container, HTTP, Flask)
```

Systemd service: `claude_vid.service` — wraps the above script for boot-time autostart.

## Frontend development (inside `frontend/`)

```bash
npm run dev          # Turbopack dev server on :3005 (requires Flask on :5102)
npm run build        # production build (also runs during Docker build)
npm run lint         # ESLint
npm run type-check   # tsc --noEmit, no emit
```

Local dev uses `.env.local` (not committed) which sets `FLASK_INTERNAL_URL=http://localhost:5102`.

## Architecture

### Request flow

```
Browser → Next.js (:3005)
  Server Components → Flask (:5102) via lib/flask.ts  (server-side, direct)
  Client Components → /api/flask/[...path]            (browser, via proxy)
                          ↓
                      Flask (:5102)
```

**Server-side data fetching** (`lib/flask.ts`): Server Components call `callFlask()` directly. Helper functions (`getBatches`, `getBatchDetail`, `getSlideshow`, etc.) fetch from Flask JSON endpoints (`/api/batches`, `/api/batch/<id>`, etc.). CSRF tokens are still extracted from Flask HTML via `parseCsrfToken()` because Flask-WTF embeds them in forms.

**Client-side mutations** (`/api/flask/[...path]/route.ts`): A transparent catch-all proxy. Forwards all HTTP methods verbatim, strips hop-by-hop headers, rewrites Flask's absolute `Location` headers to relative paths. For XHR/JSON requests, converts Flask 302 redirects into `{ redirect: "/path" }` JSON so the client can handle navigation without cross-origin issues.

- The proxy rewrites `Origin` to `https://vid.arc-codex.com` and `Referer` to `https://vid.arc-codex.com/` on every request so Flask-WTF's CSRF origin/referrer checks pass against `WTF_CSRF_TRUSTED_ORIGINS`.
- Flask's `/collection/<uuid>` route is rewritten to `/batch/<uuid>` in the Location header to match Next.js routing.
- The `/upload` path is always treated as XHR (JSON redirect) regardless of Accept header.

### Authentication

`middleware.ts` checks for the Flask `session` cookie on every non-public route. If absent, redirects to `/login?next=<path>`. The actual session is owned by Flask; Next.js is stateless.

Public routes (no cookie required): `/login`, `/register`, `/public/*`

### Data layer notes

- **Newer endpoints** return JSON directly from Flask (`/api/batches`, `/api/batch/<id>`, `/api/slideshow/<id>`, `/api/me`). Use these.
- **Legacy pattern** (still present in `lib/flask.ts`): Flask returns HTML; Next.js parses it with `cheerio` to extract batch cards and CSRF tokens via CSS selectors. Avoid expanding this pattern.
- `mediaUrl(filepath)` in `lib/flask.ts` resolves relative file paths to `/static/uploads/...` for browser consumption.

### CSRF

All Flask mutation routes (`/media/<id>/delete`, `/media/<id>/toggle_*`, `/batch/<id>/delete`, `/upload`) are decorated `@csrf.exempt`. **The frontend does not need to send a CSRF token for these.** POST with an empty `FormData()` — no token field required.

Flask-WTF still validates Origin/Referer on non-exempt routes; the proxy rewrites those headers to pass the check.

### Client-side POST pattern

For fire-and-forget mutations (toggle, delete):

```ts
try {
  await fetch(`/api/flask${url}`, {
    method: 'POST',
    credentials: 'include',
    body: new FormData(),
    redirect: 'manual',   // Flask returns 302; fetch throws NetworkError without this
  });
} catch { /* opaque redirect — ignore */ }
finally {
  window.location.reload();  // bypass Next.js cache entirely
}
```

Key points:
- `redirect: 'manual'` prevents the browser from following Flask's 302, but fetch still throws a `NetworkError` for opaque redirects — catch and ignore it.
- `window.location.reload()` in `finally` always runs and bypasses Next.js's server component cache. `router.refresh()` is not sufficient.
- For uploads, use `window.location.reload()` in finally for the same reason.

### Key types (`lib/types.ts`)

- `Batch` — id, name, itemCount; optional share/slideshow fields
- `MediaItem` — filepath, mimetype, processing_status (`completed|queued|processing|failed`), item_type (`media|blob|archive_import`)
- `SlideshowItem` — minimal subset used by the slideshow player
- `SessionUser` — username, isAdmin

### Component patterns

- Pages are Server Components; they `await cookies()` and pass the cookie header to `lib/flask.ts` fetchers.
- Interactive components (`UploadArea`, `MediaCard`, `SlideshowPlayer`) are Client Components (`'use client'`) that POST to `/api/flask/*`.
- `Navbar` is split: `Navbar` (server, fetches session user) wraps `NavbarClient` (client, handles dropdowns/interactions).
- `BatchCard` is a Client Component (despite being a card) because it owns the inline delete confirmation flow.
- Inline delete confirmation pattern (used in `MediaCard` and `BatchCard`): subtle trash icon → click shows "Delete forever" (muted) + "Keep it" (prominent bordered button), auto-cancels after 5 seconds via `useRef` timer. `cancelBtnRef` focuses "Keep it" on confirmation open so screen readers announce it immediately (`role="alert"` on the confirmation container).

### Accordion / collapsible sections (`UploadDrawer`)

Height animation without a known content height: use the CSS `grid-template-rows: 0fr → 1fr` trick.

```tsx
<div className={`grid transition-[grid-template-rows] duration-300 ${open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}>
  <div className="overflow-hidden">
    {/* content */}
  </div>
</div>
```

The outer `grid` animates `grid-template-rows`; the inner `overflow-hidden` clips the content at 0. No `max-height` magic numbers needed. Wire the toggle button with `aria-expanded` + `aria-controls={useId()}` pointing to the panel's `id`.

### SlideshowPlayer

- **Progress bar**: `barActive` boolean state drives a CSS `width` transition (`width 4s linear`). A double-rAF trick resets the bar to 0% in the DOM before the transition starts — without it the transition is skipped because the browser batches the style updates.
- **Fullscreen**: Native Fullscreen API (`requestFullscreen` / `webkitRequestFullscreen`). State is synced from `fullscreenchange` / `webkitfullscreenchange` events — never set it directly from the button click. Do not intercept Escape; the browser handles it natively and fires the change event.
- **Keyboard shortcuts**: `ArrowLeft`/`ArrowRight` navigate, `Space` toggles play/pause, `f` toggles fullscreen. Annotate buttons with `aria-keyshortcuts`. Show a persistent hint in the header (`aria-hidden="true"`).
- **Chromecast**: The Cast SDK is loaded dynamically (one `<script>` tag injected on mount). `window.__onGCastApiAvailable` is the callback the SDK calls when ready. `<google-cast-launcher>` is a custom element registered by the SDK — declare it in `declare module 'react' { namespace JSX { interface IntrinsicElements { ... } } }` (not `declare global { namespace JSX }` which doesn't work with the React 19 JSX transform). When the active slide changes and a Cast session exists, push the new media via `session.loadMedia()`. Cast only works in Chrome with the extension present and a Chromecast on the local network.

### PWA icons

Icons live in `frontend/public/icons/`. Generate them with Node + `sharp`:

```js
const sharp = require('sharp');
const fs = require('fs');
const svg = fs.readFileSync('icon.svg');
await sharp(svg).resize(512, 512).png().toFile('icon-512x512.png');
await sharp(svg).resize(192, 192).png().toFile('icon-192x192.png');
await sharp(svg).resize(180, 180).png().toFile('apple-touch-icon.png');
```

Design uses accent `#7c7cf8` on background `#0a0a10` — match these if the icon is ever regenerated. The source SVG is not committed; regenerate from the design brief if needed.

## Docker details

Three-stage build (`Dockerfile.frontend`): `deps` → `builder` → `runner` (Alpine). Output is `standalone` — only `server.js`, `.next/static`, and `public/` are in the final image. `docker-compose.yml` uses `network_mode: host` so the container can reach Flask at `localhost:5102`.
