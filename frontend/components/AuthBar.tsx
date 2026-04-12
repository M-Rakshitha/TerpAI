'use client';

import { useUser } from '@auth0/nextjs-auth0/client';

export function AuthBar() {
  const { user, isLoading } = useUser();

  return (
    <div className="flex items-center justify-end gap-3 border-b border-[#E5E7EB] bg-white px-4 py-2 text-sm text-[#374151]">
      {isLoading ? (
        <span className="text-[#94A3B8]">Checking session…</span>
      ) : user ? (
        <>
          <span className="max-w-[200px] truncate text-[#64748B]" title={user.email || user.name || undefined}>
            {user.name || user.email || 'Signed in'}
          </span>
          <a
            href="/api/auth/logout"
            className="rounded-full border border-[#E5E7EB] px-3 py-1 font-medium text-[#92400E] transition hover:bg-[#FFFBEB]"
          >
            Log out
          </a>
        </>
      ) : (
        <>
          <a
            href="/api/auth/login"
            className="rounded-full bg-[#E31937] px-4 py-1.5 font-semibold text-white transition hover:bg-[#c61631]"
          >
            Log in
          </a>
        </>
      )}
    </div>
  );
}
