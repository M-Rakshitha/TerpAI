/** Canonical app origin for redirects (Auth0 v3 uses AUTH0_BASE_URL). */
export function getAppBaseUrl(): string {
  const raw =
    process.env.AUTH0_BASE_URL || process.env.APP_BASE_URL || 'http://localhost:3000';
  return raw.replace(/\/$/, '');
}
