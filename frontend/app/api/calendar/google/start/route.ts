import { NextResponse } from 'next/server';
import { getSession } from '@auth0/nextjs-auth0';

import { getAppBaseUrl } from '@/lib/app-base-url';
import { isAuth0EnvConfigured } from '@/lib/auth0-env';
import { signGoogleOAuthState } from '@/lib/google-oauth-state';

const CALENDAR_SCOPE = 'https://www.googleapis.com/auth/calendar.events';

export const dynamic = 'force-dynamic';

export async function GET() {
  if (!isAuth0EnvConfigured()) {
    const home = new URL('/', getAppBaseUrl());
    home.searchParams.set('calendar_error', 'auth0_not_configured');
    return NextResponse.redirect(home);
  }

  const session = await getSession();
  if (!session?.user?.sub) {
    const base = getAppBaseUrl();
    const login = new URL('/api/auth/login', base);
    login.searchParams.set('returnTo', '/api/calendar/google/start');
    return NextResponse.redirect(login);
  }

  const clientId = process.env.GOOGLE_OAUTH_CLIENT_ID;
  const appBase = getAppBaseUrl();
  if (!clientId || !appBase) {
    return NextResponse.json(
      { error: 'GOOGLE_OAUTH_CLIENT_ID and AUTH0_BASE_URL (or APP_BASE_URL) must be set' },
      { status: 500 },
    );
  }

  const redirectUri = `${appBase}/api/calendar/google/callback`;
  const state = signGoogleOAuthState(session.user.sub);

  const url = new URL('https://accounts.google.com/o/oauth2/v2/auth');
  url.searchParams.set('client_id', clientId);
  url.searchParams.set('redirect_uri', redirectUri);
  url.searchParams.set('response_type', 'code');
  url.searchParams.set('scope', CALENDAR_SCOPE);
  url.searchParams.set('access_type', 'offline');
  url.searchParams.set('prompt', 'consent');
  url.searchParams.set('state', state);

  return NextResponse.redirect(url);
}
