import type { NextApiRequest, NextApiResponse } from 'next';
import { getSession } from '@auth0/nextjs-auth0';

import { isAuth0EnvConfigured } from '@/lib/auth0-env';

export default function authMe(req: NextApiRequest, res: NextApiResponse) {
  if (!isAuth0EnvConfigured()) {
    return res.status(204).end();
  }

  try {
    const session = getSession(req, res);
    if (!session?.user) {
      return res.status(204).end();
    }

    return res.status(200).json(session.user);
  } catch {
    return res.status(204).end();
  }
}
