import Link from 'next/link';
import { cookies } from 'next/headers';
import { callFlask, parseCsrfToken } from '@/lib/flask';

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next = '/' } = await searchParams;

  // Fetch Flask's login page server-side, forwarding the browser's cookies so
  // Flask generates a CSRF token bound to the existing session.
  const cookieStore = await cookies();
  const cookieHeader = cookieStore.toString();

  let csrfToken = '';
  try {
    const res = await callFlask('/login', { cookieHeader });
    if (res.status === 200) {
      csrfToken = parseCsrfToken(await res.text());
    }
  } catch {
    // Flask unreachable — render form without token; submission will surface the error.
  }

  // Pass next via query string so Flask redirects correctly after login.
  const action = next && next !== '/'
    ? `/api/flask/login?next=${encodeURIComponent(next)}`
    : '/api/flask/login';

  return (
    <div className="min-h-[calc(100dvh-3.5rem)] flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        {/* Logo mark */}
        <div className="flex justify-center mb-8">
          <div className="flex items-center gap-2 text-xl font-semibold text-txt">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-accent">
              <rect x="3" y="3" width="18" height="18" rx="2"/>
              <path d="m9 9 6 3-6 3z" fill="currentColor" stroke="none"/>
            </svg>
            LightBox
          </div>
        </div>

        <div className="card p-6 shadow-md">
          <h1 className="text-lg font-semibold text-txt mb-6 text-center">Sign in to your library</h1>

          <form action={action} method="POST" className="space-y-4">
            <input type="hidden" name="csrf_token" value={csrfToken} />
            <div>
              <label htmlFor="username" className="block text-sm text-muted mb-1">Username</label>
              <input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                required
                className="input"
                placeholder="your_username"
              />
            </div>
            <div>
              <label htmlFor="password" className="block text-sm text-muted mb-1">Password</label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                className="input"
                placeholder="••••••••"
              />
            </div>
            <button type="submit" className="btn-primary w-full mt-2">
              Sign in
            </button>
          </form>
        </div>

        <p className="text-center text-sm text-muted mt-4">
          Need an account?{' '}
          <Link href="/register" className="text-accent hover:text-accent-hover">Register</Link>
        </p>
      </div>
    </div>
  );
}
