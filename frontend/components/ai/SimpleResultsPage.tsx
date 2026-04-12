'use client'

interface SimpleResultsPageProps {
  prompt: string
  onBack: () => void
}

export default function SimpleResultsPage({ prompt, onBack }: SimpleResultsPageProps) {
  return (
    <div className="relative min-h-screen overflow-hidden px-4 py-10">
      {/* Background */}
      <div className="fixed inset-0 bg-gradient-to-br from-[#001f3f] via-[#0a0a0a] to-[#000000]" />
      <div
        className="fixed inset-0 opacity-20"
        style={{
          backgroundImage:
            'radial-gradient(ellipse at 50% 50%, rgba(227, 25, 55, 0.15) 0%, transparent 70%)'
        }}
      />

      <div className="relative z-10 mx-auto max-w-3xl">
        {/* Back Button */}
        <button
          onClick={onBack}
          className="mb-8 inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-300 hover:text-white transition-colors duration-300 hover:bg-white/5 rounded-lg"
        >
          ← Go back
        </button>

        {/* Header */}
        <div className="mb-12">
          <h1 className="text-5xl font-black text-white mb-4 tracking-tight">Your Question</h1>
          <div className="rounded-2xl bg-white/5 backdrop-blur-xl border border-white/10 p-6">
            <p className="text-lg text-gray-200 leading-relaxed">{prompt}</p>
          </div>
        </div>

        {/* Results Card */}
        <div className="rounded-3xl overflow-hidden">
          <div className="p-px bg-gradient-to-r from-[#E31937]/30 to-[#FFB81C]/20">
            <div className="rounded-3xl bg-[#1a1a1a]/80 backdrop-blur-xl shadow-2xl border border-[#E31937]/10 p-8">
              <div className="space-y-6">
                <div className="text-center">
                  <div className="inline-block">
                    <div className="w-12 h-12 bg-gradient-to-r from-[#E31937] to-[#FFB81C] rounded-full animate-spin" style={{
                      borderRadius: '50%',
                      border: '3px solid rgba(227, 25, 55, 0.2)',
                      borderTopColor: '#E31937'
                    }} />
                  </div>
                  <p className="text-gray-300 mt-4 text-lg font-medium">AI Agents are processing your question...</p>
                  <p className="text-gray-500 mt-2">This may take a few moments</p>
                </div>

                {/* Status cards */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-8">
                  {['Analyzing', 'Searching', 'Compiling'].map((stage, i) => (
                    <div
                      key={stage}
                      className="rounded-lg bg-white/5 border border-white/10 p-4 text-center animate-in fade-in"
                      style={{ animationDelay: `${i * 150}ms` }}
                    >
                      <div className="text-3xl mb-2">
                        {i === 0 ? '🔍' : i === 1 ? '📚' : '✨'}
                      </div>
                      <p className="text-sm font-medium text-gray-300">{stage}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
