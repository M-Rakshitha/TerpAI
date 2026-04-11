import React from 'react';
import { useQuery } from '@/hooks/useQuery';
import ChatInput from '@/components/chat/ChatInput';
import Dashboard from '@/components/dashboard/Dashboard';

const Page = () => {
  const { data, loading, error, submit } = useQuery();

  return (
    <div className="flex flex-col h-screen">
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <p>Loading...</p>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-full">
            <p>{error}</p>
          </div>
        ) : (
          data && <Dashboard data={data} />
        )}
      </div>
      <ChatInput onSubmit={submit} />
    </div>
  );
};

export default Page;