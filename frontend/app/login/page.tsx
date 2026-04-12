import Link from 'next/link';

export default function LoginPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#F8FAFC] px-4 text-center text-[#111827]">
      <div className="max-w-xl rounded-[32px] border border-[#E5E7EB] bg-white p-8 shadow-[0_30px_80px_-40px_rgba(17,24,39,0.2)]">
        <p className="text-sm uppercase tracking-[0.3em] text-[#92400E]">TerpAI login</p>
        <h1 className="mt-4 text-3xl font-black">Authentication is not enabled in this build</h1>
        <p className="mt-4 text-base leading-7 text-[#475569]">
          The main TerpAI prompt flow is connected directly to the backend. If you want to re-enable Auth0 later, wire the login route and client provider back in.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <Link href="/" className="rounded-full bg-[#E31937] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#c61631]">
            Go to TerpAI
          </Link>
        </div>
      </div>
    </div>
  );
}
