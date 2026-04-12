import crypto from 'crypto';

const TTL_MS = 10 * 60 * 1000;

function getSecret(): string {
  const s = process.env.AUTH0_SECRET || process.env.CALENDAR_LINK_SECRET || '';
  return s;
}

export function signGoogleOAuthState(userSub: string): string {
  const secret = getSecret();
  if (!secret) {
    throw new Error('AUTH0_SECRET (or CALENDAR_LINK_SECRET) is required to sign OAuth state');
  }
  const exp = Date.now() + TTL_MS;
  const payload = JSON.stringify({ sub: userSub, exp });
  const sig = crypto.createHmac('sha256', secret).update(payload).digest('hex');
  return Buffer.from(JSON.stringify({ sub: userSub, exp, sig }), 'utf8').toString('base64url');
}

export function verifyGoogleOAuthState(state: string, expectedSub: string): boolean {
  const secret = getSecret();
  if (!secret || !state) {
    return false;
  }
  try {
    const raw = Buffer.from(state, 'base64url').toString('utf8');
    const data = JSON.parse(raw) as { sub?: string; exp?: number; sig?: string };
    if (!data.sub || !data.exp || !data.sig) {
      return false;
    }
    if (data.sub !== expectedSub) {
      return false;
    }
    if (Date.now() > data.exp) {
      return false;
    }
    const payload = JSON.stringify({ sub: data.sub, exp: data.exp });
    const expectedSig = crypto.createHmac('sha256', secret).update(payload).digest('hex');
    const a = Buffer.from(data.sig, 'hex');
    const b = Buffer.from(expectedSig, 'hex');
    if (a.length !== b.length) {
      return false;
    }
    return crypto.timingSafeEqual(a, b);
  } catch {
    return false;
  }
}
