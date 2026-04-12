import Link from 'next/link';

export default function LoginPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#F8FAFC] px-4 text-center text-[#111827]">
      <div className="max-w-xl rounded-[32px] border border-[#E5E7EB] bg-white p-8 shadow-[0_30px_80px_-40px_rgba(17,24,39,0.2)]">
        <p className="text-sm uppercase tracking-[0.3em] text-[#92400E]">CampusPilot login</p>
        <h1 className="mt-4 text-3xl font-black">Sign in with Auth0</h1>
        <p className="mt-4 text-base leading-7 text-[#475569]">
          Use your Auth0 account to save campus events to Google Calendar and access secured APIs. Set{' '}
          <code className="rounded bg-[#F1F5F9] px-1">AUTH0_BASE_URL</code> (or{' '}
          <code className="rounded bg-[#F1F5F9] px-1">APP_BASE_URL</code>), Auth0 application variables, and Google OAuth
          credentials per the project README.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <a
            href="/api/auth/login"
            className="rounded-full bg-[#E31937] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#c61631]"
          >
            Continue to Auth0
          </a>
          <Link
            href="/"
            className="rounded-full border border-[#E5E7EB] px-5 py-3 text-sm font-semibold text-[#374151] transition hover:bg-[#F8FAFC]"
          >
            Back to CampusPilot
          </Link>
        </div>
      </div>
    </div>
  );
}
