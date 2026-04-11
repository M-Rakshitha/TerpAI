import { useState } from 'react';
import { QueryResponse } from '@/lib/types';
import { MOCK_RESPONSE } from '@/lib/mockData';

export function useQuery() {
  const [data, setData] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(message: string) {
    setLoading(true);
    setError(null);
    try {
      // Simulate API call with 1 second dela
      await new Promise(resolve => setTimeout(resolve, 1000));
      setData(MOCK_RESPONSE);
    } catch (e) {
      setError('Something went wrong. Try again.');
    } finally {
      setLoading(false);
    }
  }

  return { data, loading, error, submit };
}