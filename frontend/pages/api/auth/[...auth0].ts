import type { NextApiRequest, NextApiResponse } from 'next';
import { handleAuth } from '@auth0/nextjs-auth0';

import { isAuth0EnvConfigured } from '@/lib/auth0-env';

const authHandler = handleAuth();

export default async function auth(req: NextApiRequest, res: NextApiResponse) {
  if (!isAuth0EnvConfigured()) {
    return res.status(503).json({
      error:
        'Auth0 is not configured. Add AUTH0_SECRET, AUTH0_BASE_URL, AUTH0_ISSUER_BASE_URL, AUTH0_CLIENT_ID, and AUTH0_CLIENT_SECRET to .env.local.',
    });
  }

  await authHandler(req, res);
}
