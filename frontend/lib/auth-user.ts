import { NextRequest } from 'next/server';

export type AuthUser = {
  sub: string;
  email?: string;
  name?: string;
};

export async function getAuthUserFromRequest(request: NextRequest): Promise<AuthUser | null> {
  const meUrl = new URL('/api/auth/me', request.url);
  const res = await fetch(meUrl, {
    headers: { cookie: request.headers.get('cookie') ?? '' },
    cache: 'no-store',
  });

  if (!res.ok) {
    return null;
  }

  const json = (await res.json().catch(() => null)) as Partial<AuthUser> | null;
  if (!json?.sub) {
    return null;
  }

  return {
    sub: json.sub,
    email: json.email,
    name: json.name,
  };
}
