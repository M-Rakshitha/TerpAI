import { QueryResponse, QueryTimelineEvent } from './types';

const DEFAULT_API_BASE_URL = 'http://localhost:8000';

function getApiBaseUrl() {
  return (process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_BASE_URL).replace(/\/$/, '');
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

export async function submitQuery(message: string): Promise<QueryResponse> {
  const response = await fetch(`${getApiBaseUrl()}/api/query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message }),
  });

  if (!response.ok) {
    const detail = await readErrorResponse(response);
    throw new Error(detail || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as QueryResponse;
}

async function submitQueryViaWebSocket(
  message: string,
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
  onEvent?: (event: QueryTimelineEvent) => void,
): Promise<QueryResponse> {
  try {
    return await submitQueryViaWebSocket(message, onEvent);
  } catch {
    // Real-data fallback path: use HTTP query endpoint if websocket stream is unavailable.
    return submitQuery(message);
  }
}