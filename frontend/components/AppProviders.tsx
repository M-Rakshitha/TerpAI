'use client';

import type { ReactNode } from 'react';
import { UserProvider } from '@auth0/nextjs-auth0';

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <UserProvider>
      {children}
    </UserProvider>
  );
}
