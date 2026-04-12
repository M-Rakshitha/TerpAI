import { QueryResponse, QueryTimelineEvent } from './types';

export interface QuerySubmitContext {
  location?: { lat: number; lng: number } | null;
  user_location?: string;
  current_location_coords?: { latitude: number; longitude: number };
  location_permission_granted?: boolean;
}

const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000';
const LOCAL_FALLBACK_API_URLS = [
  'http://127.0.0.1:8000',
  'http://localhost:8000',
  'http://127.0.0.1:8020',
  'http://localhost:8020',
];

function getApiBaseUrl() {
  return (process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_BASE_URL).replace(/\/$/, '');
}

function getApiBaseUrlCandidates() {
  const configured = getApiBaseUrl();
  return Array.from(new Set([configured, ...LOCAL_FALLBACK_API_URLS]));
}

function buildWebSocketUrl(baseApiUrl: string) {
  const baseUrl = new URL(baseApiUrl);
  baseUrl.protocol = baseUrl.protocol === 'https:' ? 'wss:' : 'ws:';
  baseUrl.pathname = '/ws/query';
  baseUrl.search = '';
  baseUrl.hash = '';
  return baseUrl.toString();
}

async function readErrorResponse(response: Response) {
  try {
    return await response.text();
  } catch {
    return '';
  }
}

export async function submitQuery(message: string, submitContext?: QuerySubmitContext): Promise<QueryResponse> {
  const candidates = getApiBaseUrlCandidates();
  const requestBody = JSON.stringify(buildRequestPayload(message, submitContext));
  let lastError: Error | null = null;

  for (const baseUrl of candidates) {
    try {
      const response = await fetch(`${baseUrl}/api/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: requestBody,
      });

      if (!response.ok) {
        const detail = await readErrorResponse(response);
        lastError = new Error(detail || `Request failed with status ${response.status}`);
        continue;
      }

      return (await response.json()) as QueryResponse;
    } catch (error) {
      lastError = error instanceof Error ? error : new Error('Network request failed');
      continue;
    }
  }

  throw lastError || new Error('Unable to reach backend API.');
}

function buildRequestPayload(message: string, submitContext?: QuerySubmitContext) {
  const normalizedLocation = submitContext?.location ?? null;
  const derivedCoords =
    normalizedLocation
      ? {
          latitude: normalizedLocation.lat,
          longitude: normalizedLocation.lng,
        }
      : submitContext?.current_location_coords;
  const derivedUserLocation =
    normalizedLocation
      ? `${normalizedLocation.lat},${normalizedLocation.lng}`
      : submitContext?.user_location;

  return {
    message,
    location: normalizedLocation,
    ...(derivedUserLocation ? { user_location: derivedUserLocation } : {}),
    ...(derivedCoords ? { current_location_coords: derivedCoords } : {}),
    ...(typeof submitContext?.location_permission_granted === 'boolean'
      ? { location_permission_granted: submitContext.location_permission_granted }
      : {}),
  };
}

async function submitQueryViaWebSocket(
  message: string,
  submitContext?: QuerySubmitContext,
  onEvent?: (event: QueryTimelineEvent) => void,
): Promise<QueryResponse> {
  const candidates = getApiBaseUrlCandidates();
  let lastError: Error | null = null;

  for (const baseUrl of candidates) {
    try {
      const response = await new Promise<QueryResponse>((resolve, reject) => {
        const socket = new WebSocket(buildWebSocketUrl(baseUrl));
        let resolved = false;

        const finish = (queryResponse: QueryResponse) => {
          if (resolved) {
            return;
          }
          resolved = true;
          try {
            socket.close();
          } catch {
            // ignore close errors in fallback paths
          }
          resolve(queryResponse);
        };

        socket.onopen = () => {
          socket.send(
            JSON.stringify({
              ...buildRequestPayload(message, submitContext),
              request_id: crypto.randomUUID?.() || `${Date.now()}`,
              debug_trace_context: true,
            }),
          );
        };

        socket.onmessage = (event) => {
          try {
            const parsed = JSON.parse(String(event.data)) as QueryTimelineEvent;
            onEvent?.(parsed);

            if (parsed.type === 'query_result' && parsed.payload && typeof parsed.payload === 'object') {
              finish(parsed.payload as QueryResponse);
            }
          } catch (error) {
            reject(error);
          }
        };

        socket.onerror = () => {
          reject(new Error(`WebSocket connection failed for ${baseUrl}`));
        };

        socket.onclose = () => {
          if (!resolved) {
            reject(new Error(`WebSocket closed before a final response arrived for ${baseUrl}`));
          }
        };
      });

      return response;
    } catch (error) {
      lastError = error instanceof Error ? error : new Error('WebSocket connection failed');
    }
  }

  throw lastError || new Error('Unable to reach backend websocket.');
}

export async function submitQueryWithProgress(
  message: string,
  submitContext?: QuerySubmitContext,
  onEvent?: (event: QueryTimelineEvent) => void,
): Promise<QueryResponse> {
  try {
    return await submitQueryViaWebSocket(message, submitContext, onEvent);
  } catch {
    // Real-data fallback path: use HTTP query endpoint if websocket stream is unavailable.
    return submitQuery(message, submitContext);
  }
}
