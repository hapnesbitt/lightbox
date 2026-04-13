'use client';

import Link from 'next/link';
import { useState } from 'react';

interface NavbarClientProps {
  username: string | null;
}

export function NavbarClient({ username }: NavbarClientProps) {
  const [menuOpen, setMenuOpen] = useState(false);

  function handleLogout() {
    window.location.href = '/logout';
  }

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-card/95 backdrop-blur-sm">
      <nav className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between gap-4">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 font-semibold text-txt hover:text-accent-hover transition-colors">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-accent" aria-hidden>
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <path d="m9 9 6 3-6 3z" fill="currentColor" stroke="none"/>
          </svg>
          <span>LightBox</span>
        </Link>

        {/* Right side */}
        {username ? (
          <div className="relative">
            <button
              onClick={() => setMenuOpen((v) => !v)}
              className="flex items-center gap-2 px-3 py-1.5 rounded border border-border text-sm text-muted hover:text-txt hover:border-faint transition-colors"
              aria-expanded={menuOpen}
              aria-haspopup="menu"
              aria-controls="user-menu"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <circle cx="12" cy="8" r="4"/>
                <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
              </svg>
              <span>{username}</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="m6 9 6 6 6-6"/>
              </svg>
            </button>

            {menuOpen && (
              <>
                {/* backdrop */}
                <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} aria-hidden />
                <div id="user-menu" role="menu" aria-label="User menu"
                  className="absolute right-0 top-full mt-1 z-20 w-44 bg-card border border-border rounded-lg shadow-md py-1">
                  <Link
                    href="/"
                    role="menuitem"
                    onClick={() => setMenuOpen(false)}
                    className="flex items-center gap-2 px-4 py-2 text-sm text-muted hover:text-txt hover:bg-card-hover transition-colors"
                  >
                    My Library
                  </Link>
                  <hr className="my-1 border-border" aria-hidden="true" />
                  <button
                    role="menuitem"
                    onClick={() => handleLogout()}
                    className="w-full flex items-center gap-2 px-4 py-2 text-sm text-danger/80 hover:text-danger hover:bg-danger/10 transition-colors"
                  >
                    Sign out
                  </button>
                </div>
              </>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <Link href="/login" className="btn-ghost text-sm px-3 py-1.5">Sign in</Link>
            <Link href="/register" className="btn-primary text-sm px-3 py-1.5">Register</Link>
          </div>
        )}
      </nav>
    </header>
  );
}
