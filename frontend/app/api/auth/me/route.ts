import { NextResponse } from 'next/server';
import { getSession } from '@auth0/nextjs-auth0';

import { isAuth0EnvConfigured } from '@/lib/auth0-env';

export const dynamic = 'force-dynamic';

/**
 * Dedicated route so `/api/auth/me` wins over `auth/[auth0]` and we can short-circuit
 * when Auth0 env is missing (SDK otherwise returns 500: "secret" is not allowed to be empty).
 */
export async function GET() {
  if (!isAuth0EnvConfigured()) {
    return new NextResponse(null, { status: 204 });
  }

  try {
    const session = await getSession();
    if (!session?.user) {
      return new NextResponse(null, { status: 204 });
    }
    return NextResponse.json(session.user);
  } catch {
    return new NextResponse(null, { status: 204 });
  }
}
