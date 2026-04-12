import { NextRequest, NextResponse } from 'next/server';
import { getSession } from '@auth0/nextjs-auth0';

import { isAuth0EnvConfigured } from '@/lib/auth0-env';
import { getBackendBaseUrl } from '@/lib/backend-server';

export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
  if (!isAuth0EnvConfigured()) {
    return NextResponse.json({ error: 'Auth0 is not configured' }, { status: 503 });
  }

  const session = await getSession();
  if (!session?.user?.sub) {
    return NextResponse.json({ error: 'Not signed in' }, { status: 401 });
  }

  const linkSecret = process.env.CALENDAR_LINK_SECRET;
  if (!linkSecret) {
    return NextResponse.json({ error: 'Calendar linking is not configured' }, { status: 503 });
  }

  let payload: Record<string, unknown>;
  try {
    payload = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const backend = getBackendBaseUrl();
  const res = await fetch(`${backend}/api/integrations/google-calendar/events/link`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-TerpAI-Calendar-Secret': linkSecret,
    },
    body: JSON.stringify({
      user_sub: session.user.sub,
      title: payload.title,
      location: payload.location ?? null,
      start: payload.start,
      end: payload.end ?? null,
      description: payload.description ?? null,
    }),
  });

  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }

  return NextResponse.json(data, { status: res.status });
}
