import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-16 text-white">
      <div className="max-w-xl rounded-[36px] border border-[#E31937]/20 bg-[#1a1a1a]/90 p-8 text-center shadow-2xl shadow-black/20 backdrop-blur-2xl">
        <p className="text-sm uppercase tracking-[0.3em] text-[#FFB81C]">CampusPilot</p>
        <h1 className="mt-3 text-4xl font-black text-white">Page not found</h1>
        <p className="mt-4 text-base leading-7 text-gray-300">
          The page you requested does not exist or has moved.
        </p>
        <div className="mt-8 flex justify-center">
          <Link
            href="/"
            className="inline-flex items-center justify-center rounded-[28px] border border-[#F59E0B]/40 bg-[#111827] px-6 py-3 text-sm font-semibold text-[#FDE68A] shadow-lg shadow-black/30 transition hover:border-[#FBBF24] hover:bg-[#1f2937] hover:text-[#FEF3C7]"
          >
            Go home
          </Link>
        </div>
      </div>
    </div>
  )
}