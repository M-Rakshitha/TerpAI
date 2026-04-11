import React from 'react';

const Layout: React.FC = ({ children }) => {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-gray-800 text-white p-4">
        <h1 className="text-xl">TerpAI</h1>
      </header>
      <main className="flex-grow">
        {children}
      </main>
      <footer className="bg-gray-800 text-white p-4 text-center">
        <p>&copy; {new Date().getFullYear()} TerpAI. All rights reserved.</p>
      </footer>
    </div>
  );
};

export default Layout;