/**
 * Server-side backend base URL for BFF routes (calendar, etc.).
 */
export function getBackendBaseUrl(): string {
  const url =
    process.env.NEXT_PUBLIC_API_URL || process.env.API_URL || 'https://terpai-4.onrender.com';
  return url.replace(/\/$/, '');
}
