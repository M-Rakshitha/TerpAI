import { handleAuth } from '@auth0/nextjs-auth0';
import type { NextRequest } from 'next/server';
import { NextResponse } from 'next/server';

import { isAuth0EnvConfigured } from '@/lib/auth0-env';

export const dynamic = 'force-dynamic';

const runAuth = handleAuth();

export async function GET(req: NextRequest, ctx: { params: { auth0: string | string[] } }) {
  if (!isAuth0EnvConfigured()) {
    return NextResponse.json(
      {
        error:
          'Auth0 is not configured. Add AUTH0_SECRET, AUTH0_BASE_URL, AUTH0_ISSUER_BASE_URL, AUTH0_CLIENT_ID, and AUTH0_CLIENT_SECRET to .env.local.',
      },
      { status: 503 },
    );
  }

  return runAuth(req, ctx);
}
