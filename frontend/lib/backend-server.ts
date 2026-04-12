/**
 * Server-side backend base URL for BFF routes (calendar, etc.).
 */
export function getBackendBaseUrl(): string {
  const url = process.env.NEXT_PUBLIC_API_URL || process.env.API_URL || 'http://127.0.0.1:8000';
  return url.replace(/\/$/, '');
}
