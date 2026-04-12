'use client';

import type { ReactNode } from 'react';
import { UserProvider } from '@auth0/nextjs-auth0/client';

import { AuthBar } from '@/components/AuthBar';

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <UserProvider>
      <AuthBar />
      {children}
    </UserProvider>
  );
}
