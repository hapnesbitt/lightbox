import Link from 'next/link';
import { cookies } from 'next/headers';
import { getSessionUser } from '@/lib/flask';

async function NavbarServer() {
  const cookieStore = await cookies();
  const cookieHeader = cookieStore.toString();

  let username: string | null = null;
  if (cookieHeader) {
    try {
      const user = await getSessionUser(cookieHeader);
      username = user?.username ?? null;
    } catch {
      // unauthenticated or Flask down — render logged-out nav
    }
  }

  return <NavbarClient username={username} />;
}

// Client component for interactive dropdown
import { NavbarClient } from './NavbarClient';

export function Navbar() {
  return <NavbarServer />;
}
