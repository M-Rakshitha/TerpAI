import { NextResponse } from 'next/server';
import { getSession } from '@auth0/nextjs-auth0';

import { isAuth0EnvConfigured } from '@/lib/auth0-env';
import { getBackendBaseUrl } from '@/lib/backend-server';

export const dynamic = 'force-dynamic';

export async function GET() {
  if (!isAuth0EnvConfigured()) {
    return NextResponse.json({
      authenticated: false,
      connected: false,
      configured: false,
      error: 'auth0_not_configured',
    });
  }

  const session = await getSession();
  if (!session?.user?.sub) {
    return NextResponse.json({ authenticated: false, connected: false });
  }

  const linkSecret = process.env.CALENDAR_LINK_SECRET;
  if (!linkSecret) {
    return NextResponse.json({ authenticated: true, connected: false, configured: false });
  }

  const backend = getBackendBaseUrl();
  const url = new URL(`${backend}/api/integrations/google-calendar/status/link`);
  url.searchParams.set('user_sub', session.user.sub);

  const res = await fetch(url.toString(), {
    headers: { 'X-TerpAI-Calendar-Secret': linkSecret },
    cache: 'no-store',
  });

  if (!res.ok) {
    return NextResponse.json({ authenticated: true, connected: false, error: 'status_failed' });
  }

  const data = (await res.json()) as { connected?: boolean };
  return NextResponse.json({
    authenticated: true,
    connected: Boolean(data.connected),
    configured: true,
  });
}
