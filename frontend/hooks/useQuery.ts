import { useState } from 'react';
import { queryTerpAI } from '@/lib/api';
import { QueryResponse } from '@/lib/types';

export function useQuery() {
  const [data, setData] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(message: string) {
    setLoading(true);
    setError(null);
    try {
      const result = await queryTerpAI(message);
      setData(result);
    } catch (e) {
      setError('Something went wrong. Try again.');
    } finally {
      setLoading(false);
    }
  }

  return { data, loading, error, submit };
}