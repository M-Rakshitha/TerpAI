import { NextPage } from 'next';
import { useUser } from '@auth0/nextjs-auth0';
import Link from 'next/link';

const LoginPage: NextPage = () => {
  const { user, isLoading } = useUser();

  if (isLoading) {
    return <div>Loading...</div>;
  }

  if (user) {
    return (
      <div>
        <h1>Welcome, {user.name}!</h1>
        <Link href="/">Go to Dashboard</Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center h-screen">
      <h1 className="text-2xl font-bold mb-4">Login</h1>
      <a href="/api/auth/login" className="bg-blue-500 text-white px-4 py-2 rounded">
        Log in with Auth0
      </a>
    </div>
  );
};

export default LoginPage;