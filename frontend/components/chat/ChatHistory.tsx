import React from 'react';

interface ChatHistoryProps {
  messages: string[];
}

const ChatHistory: React.FC<ChatHistoryProps> = ({ messages }) => {
  return (
    <div className="chat-history">
      {messages.length === 0 ? (
        <p>No chat history available.</p>
      ) : (
        <ul>
          {messages.map((message, index) => (
            <li key={index} className="chat-message">
              {message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default ChatHistory;