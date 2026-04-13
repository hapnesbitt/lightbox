'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

export default function RegisterPage() {
  const router = useRouter();
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    setSuccess('');
    setLoading(true);

    const form = e.currentTarget;
    const formData = new FormData(form);

    if (formData.get('password') !== formData.get('confirm_password')) {
      setError('Passwords do not match.');
      setLoading(false);
      return;
    }

    try {
      // Get CSRF token first
      const pageRes = await fetch('/api/flask/register', { credentials: 'include' });
      const pageHtml = await pageRes.text();
      const csrfMatch = pageHtml.match(/name=["']csrf_token["']\s+value=["']([^"']+)["']/);
      if (csrfMatch?.[1]) formData.set('csrf_token', csrfMatch[1]);

      const res = await fetch('/api/flask/register', {
        method: 'POST',
        credentials: 'include',
        body: formData,
        redirect: 'manual',
      });

      // Flask redirects to /login on successful registration
      if (res.type === 'opaqueredirect') {
        setSuccess('Account created! You can now sign in.');
        setTimeout(() => router.push('/login'), 1500);
        return;
      }

      const html = await res.text();
      const errMatch = html.match(/class="[^"]*alert-danger[^"]*"[^>]*>\s*([^<]+)/);
      setError(errMatch?.[1]?.trim() ?? 'Registration failed. Username may already be taken.');
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-[calc(100dvh-3.5rem)] flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
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
          <h1 className="text-lg font-semibold text-txt mb-6 text-center">Create an account</h1>

          {error && (
            <div className="mb-4 px-3 py-2 rounded bg-danger/15 border border-danger/30 text-danger text-sm" role="alert">
              {error}
            </div>
          )}
          {success && (
            <div className="mb-4 px-3 py-2 rounded bg-success/15 border border-success/30 text-success text-sm" role="status">
              {success}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="username" className="block text-sm text-muted mb-1">Username</label>
              <input id="username" name="username" type="text" autoComplete="username" required
                className="input" placeholder="choose_a_username" />
            </div>
            <div>
              <label htmlFor="password" className="block text-sm text-muted mb-1">Password</label>
              <input id="password" name="password" type="password" autoComplete="new-password" required
                className="input" placeholder="••••••••" minLength={6} />
            </div>
            <div>
              <label htmlFor="confirm_password" className="block text-sm text-muted mb-1">Confirm password</label>
              <input id="confirm_password" name="confirm_password" type="password" autoComplete="new-password" required
                className="input" placeholder="••••••••" />
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full mt-2">
              {loading ? 'Creating account…' : 'Create account'}
            </button>
          </form>
        </div>

        <p className="text-center text-sm text-muted mt-4">
          Already have an account?{' '}
          <Link href="/login" className="text-accent hover:text-accent-hover">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
