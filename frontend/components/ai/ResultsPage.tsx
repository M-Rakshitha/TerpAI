'use client'

interface ResultsPageProps {
  prompt: string
  result: string
  onReset: () => void
}

export default function ResultsPage({ prompt, result, onReset }: ResultsPageProps) {
  return (
    <div className="relative min-h-screen overflow-hidden bg-[#F8FAFC] px-4 py-10 text-[#111827]">
      {/* Animated background blobs */}
      <div
        className="absolute top-0 right-0 -mr-32 -mt-32 h-72 w-72 rounded-full bg-[#E31937]/8 blur-3xl"
      />
      <div
        className="absolute bottom-0 left-0 -ml-40 -mb-40 h-80 w-80 rounded-full bg-[#FFB81C]/8 blur-3xl"
      />

      <div className="relative mx-auto w-full max-w-6xl space-y-8">
        <div
          className="rounded-[36px] border border-[#E31937]/10 bg-white/95 p-8 shadow-[0_35px_100px_-45px_rgba(227,25,55,0.3)] backdrop-blur-xl"
        >
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p
                className="text-sm uppercase tracking-[0.28em] text-[#92400E]"
              >
                Final campus answer
              </p>
              <h2
                className="mt-2 text-4xl font-black"
              >
                Aggregated Results
              </h2>
              <p
                className="mt-3 max-w-2xl text-base leading-7 text-[#475569]"
              >
                The Aggregation Agent combined the outputs from all campus agents and turned them into a clear, student-ready result.
              </p>
            </div>
            <button
              onClick={onReset}
              className="inline-flex items-center justify-center rounded-[28px] border border-[#E31937] bg-white px-6 py-3 text-sm font-semibold text-[#E31937] transition hover:bg-[#FEF2F2]"
            >
              Ask another question
            </button>
          </div>

          <div className="mt-10 grid gap-6 lg:grid-cols-3">
            <div
              className="rounded-[32px] border border-[#E31937]/10 bg-[#FFFBEB] p-6 shadow-sm hover:shadow-lg transition-shadow"
            >
              <p
                className="text-xs uppercase tracking-[0.3em] text-[#92400E]"
              >
                Campus prompt
              </p>
              <p className="mt-4 text-lg font-semibold text-[#111827]">
                {prompt}
              </p>
            </div>

            <div
              className="rounded-[32px] border border-[#E31937]/10 bg-white p-6 shadow-sm hover:shadow-lg transition-shadow"
            >
              <p
                className="text-xs uppercase tracking-[0.3em] text-[#475569]"
                animate={{ opacity: [0.7, 1, 0.7] }}
                transition={{ duration: 2, repeat: Infinity, delay: 0.2 }}
              >
                Final answer
              </p>
              <p className="mt-4 text-lg font-semibold text-[#111827]">
                {result}
              </p>
            </div>

            <div
              className="rounded-[32px] border border-[#E31937]/10 bg-[#F0F9FF] p-6 shadow-sm hover:shadow-lg transition-shadow"
            >
              <p
                className="text-xs uppercase tracking-[0.3em] text-[#1D4ED8]"
              >
                Ready to use
              </p>
              <h3 className="mt-4 text-lg font-semibold text-[#111827]">Campus-ready summary</h3>
              <p className="mt-3 text-sm text-[#475569]">
                Perfect for quick decisions on dining, directions, and campus activities.
              </p>
            </div>
          </div>

          <div
            className="mt-8 rounded-[32px] border border-[#E31937]/10 bg-white p-6 shadow-sm"
          >
            <h3 className="text-xl font-semibold text-[#111827]">TerpAI visualization</h3>
            <div className="mt-4 space-y-5">
              <div
                className="rounded-[28px] bg-[#FFFBEB] p-5 shadow-sm hover:scale-105 hover:translate-x-2 transition-transform"
              >
                <p
                  className="text-sm uppercase tracking-[0.25em] text-[#92400E]"
                >
                  UMD Recommendation
                </p>
                <p className="mt-3 text-base leading-7 text-[#475569]">
                  The result is tailored for a college student looking for fast, campus-aware answers with a friendly flow.
                </p>
              </div>
              <div
                className="rounded-[28px] bg-[#F0F9FF] p-5 shadow-sm hover:scale-105 hover:translate-x-2 transition-transform"
              >
                <p
                  className="text-sm uppercase tracking-[0.25em] text-[#1D4ED8]"
                >
                  Actionable Insight
                </p>
                <p className="mt-3 text-base leading-7 text-[#475569]">
                  Use this page to see the final recommendation and move quickly from question to decision.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
