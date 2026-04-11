import React, { useState } from 'react';
import { useQuery } from '@/hooks/useQuery';
import { Button } from '@/components/ui/Button'; // Assuming you have a Button component in your UI folder

const ChatInput: React.FC = () => {
  const [input, setInput] = useState('');
  const { loading, submit } = useQuery();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim()) {
      submit(input);
      setInput('');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="fixed bottom-0 left-0 right-0 p-4 bg-white dark:bg-gray-800">
      <div className="flex">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          className="flex-grow p-2 border rounded-l-md"
          placeholder="Type your message..."
          disabled={loading}
        />
        <Button type="submit" disabled={loading} className="ml-2">
          {loading ? 'Sending...' : 'Send'}
        </Button>
      </div>
      {loading && <div className="spinner">Loading...</div>} {/* Replace with your loading spinner */}
    </form>
  );
};

export default ChatInput;