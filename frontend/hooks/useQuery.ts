import { useState } from 'react';
import { QuerySubmitContext, submitQueryWithProgress } from '@/lib/api';
import { QueryResponse, QueryTimelineEvent } from '@/lib/types';

export function useQuery() {
  const [data, setData] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<QueryTimelineEvent[]>([]);

  async function submit(message: string, submitContext?: QuerySubmitContext) {
    setLoading(true);
    setError(null);
    setData(null);
    setEvents([]);
    try {
      const response = await submitQueryWithProgress(message, submitContext, (event) => {
        setEvents((current) => [...current, event]);
      });
      setData(response);
      return response;
    } catch (e) {
      const messageText = e instanceof Error ? e.message : 'Something went wrong. Try again.';
      setError(messageText);
      throw e;
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setData(null);
    setLoading(false);
    setError(null);
    setEvents([]);
  }

  return { data, loading, error, events, submit, reset };
}