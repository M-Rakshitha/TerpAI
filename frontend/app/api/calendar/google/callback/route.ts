import { NextRequest, NextResponse } from 'next/server';
import { getSession } from '@auth0/nextjs-auth0';

import { getAppBaseUrl } from '@/lib/app-base-url';
import { isAuth0EnvConfigured } from '@/lib/auth0-env';
import { getBackendBaseUrl } from '@/lib/backend-server';
import { verifyGoogleOAuthState } from '@/lib/google-oauth-state';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  if (!isAuth0EnvConfigured()) {
    const home = new URL('/', getAppBaseUrl());
    home.searchParams.set('calendar_error', 'auth0_not_configured');
    return NextResponse.redirect(home);
  }

  const session = await getSession();
  if (!session?.user?.sub) {
    const base = getAppBaseUrl();
    return NextResponse.redirect(new URL('/api/auth/login', base));
  }

  const { searchParams } = new URL(request.url);
  const code = searchParams.get('code');
  const state = searchParams.get('state');
  const err = searchParams.get('error');

  const appBase = getAppBaseUrl();
  const home = new URL('/', appBase);

  if (err) {
    home.searchParams.set('calendar_error', err);
    return NextResponse.redirect(home);
  }

  if (!code || !state) {
    home.searchParams.set('calendar_error', 'missing_code');
    return NextResponse.redirect(home);
  }

  if (!verifyGoogleOAuthState(state, session.user.sub)) {
    home.searchParams.set('calendar_error', 'invalid_state');
    return NextResponse.redirect(home);
  }

  const clientId = process.env.GOOGLE_OAUTH_CLIENT_ID;
  const clientSecret = process.env.GOOGLE_OAUTH_CLIENT_SECRET;
  const redirectUri = `${appBase.replace(/\/$/, '')}/api/calendar/google/callback`;

  if (!clientId || !clientSecret) {
    home.searchParams.set('calendar_error', 'server_config');
    return NextResponse.redirect(home);
  }

  const body = new URLSearchParams({
    code,
    client_id: clientId,
    client_secret: clientSecret,
    redirect_uri: redirectUri,
    grant_type: 'authorization_code',
  });

  const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });

  const tokenJson = (await tokenRes.json()) as { refresh_token?: string; error?: string };
  if (!tokenRes.ok || !tokenJson.refresh_token) {
    home.searchParams.set(
      'calendar_error',
      tokenJson.error || 'no_refresh_token',
    );
    return NextResponse.redirect(home);
  }

  const linkSecret = process.env.CALENDAR_LINK_SECRET;
  if (!linkSecret) {
    home.searchParams.set('calendar_error', 'missing_link_secret');
    return NextResponse.redirect(home);
  }

  const backend = getBackendBaseUrl();
  const linkRes = await fetch(`${backend}/api/integrations/google-calendar/token/link`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-TerpAI-Calendar-Secret': linkSecret,
    },
    body: JSON.stringify({
      user_sub: session.user.sub,
      refresh_token: tokenJson.refresh_token,
    }),
  });

  if (!linkRes.ok) {
    home.searchParams.set('calendar_error', 'backend_store_failed');
    return NextResponse.redirect(home);
  }

  home.searchParams.set('calendar', 'connected');
  return NextResponse.redirect(home);
}
