import { NextResponse } from 'next/server';
import { NextRequest } from 'next/server';

import { getAppBaseUrl } from '@/lib/app-base-url';
import { isAuth0EnvConfigured } from '@/lib/auth0-env';
import { getAuthUserFromRequest } from '@/lib/auth-user';
import { signGoogleOAuthState } from '@/lib/google-oauth-state';

const CALENDAR_SCOPE = 'https://www.googleapis.com/auth/calendar.events';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  if (!isAuth0EnvConfigured()) {
    const home = new URL('/', getAppBaseUrl());
    home.searchParams.set('calendar_error', 'auth0_not_configured');
    return NextResponse.redirect(home);
  }

  const user = await getAuthUserFromRequest(request);
  if (!user?.sub) {
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
  const state = signGoogleOAuthState(user.sub);

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
