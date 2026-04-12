import { QueryResponse, QueryTimelineEvent } from './types';

export interface QuerySubmitContext {
  user_location?: string;
  current_location_coords?: { latitude: number; longitude: number };
  location_permission_granted?: boolean;
}

const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8020';
const LOCAL_FALLBACK_API_URLS = ['http://127.0.0.1:8020', 'http://localhost:8000'];

function getApiBaseUrl() {
  return (process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_BASE_URL).replace(/\/$/, '');
}

function getApiBaseUrlCandidates() {
  const configured = getApiBaseUrl();
  return Array.from(new Set([configured, ...LOCAL_FALLBACK_API_URLS]));
}

function buildWebSocketUrl() {
  const baseUrl = new URL(getApiBaseUrl());
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
  const requestBody = JSON.stringify({
    message,
    ...(submitContext?.user_location ? { user_location: submitContext.user_location } : {}),
    ...(submitContext?.current_location_coords
      ? { current_location_coords: submitContext.current_location_coords }
      : {}),
    ...(typeof submitContext?.location_permission_granted === 'boolean'
      ? { location_permission_granted: submitContext.location_permission_granted }
      : {}),
  });
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

async function submitQueryViaWebSocket(
  message: string,
  submitContext?: QuerySubmitContext,
  onEvent?: (event: QueryTimelineEvent) => void,
): Promise<QueryResponse> {
  return new Promise<QueryResponse>((resolve, reject) => {
    const socket = new WebSocket(buildWebSocketUrl());
    let resolved = false;

    const finish = (response: QueryResponse) => {
      if (resolved) {
        return;
      }
      resolved = true;
      try {
        socket.close();
      } catch {
        // ignore close errors in fallback paths
      }
      resolve(response);
    };

    socket.onopen = () => {
      socket.send(
        JSON.stringify({
          message,
          request_id: crypto.randomUUID?.() || `${Date.now()}`,
          debug_trace_context: true,
          ...(submitContext?.user_location ? { user_location: submitContext.user_location } : {}),
          ...(submitContext?.current_location_coords
            ? { current_location_coords: submitContext.current_location_coords }
            : {}),
          ...(typeof submitContext?.location_permission_granted === 'boolean'
            ? { location_permission_granted: submitContext.location_permission_granted }
            : {}),
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
      reject(new Error('WebSocket connection failed'));
    };

    socket.onclose = () => {
      if (!resolved) {
        reject(new Error('WebSocket closed before a final response arrived'));
      }
    };
  });
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