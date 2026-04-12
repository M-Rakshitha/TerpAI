/**
 * Auth0 SDK throws if initialized with an empty AUTH0_SECRET. Use this guard
 * before calling getSession/handleAuth so local/dev without .env still works.
 */
export function isAuth0EnvConfigured(): boolean {
  return Boolean(process.env.AUTH0_SECRET?.trim());
}
