'use client'

import { useState } from 'react'

interface PromptPageProps {
  onSubmit: (prompt: string) => void
}

const suggestionChips = [
  { text: 'Where can I find vegetarian food nearby?', icon: '🥗' },
  { text: 'What are the quiet study spots on campus?', icon: '📚' },
  { text: 'How do I get to the library?', icon: '🗺️' },
  { text: 'What events are happening this weekend?', icon: '🎉' },
  { text: "Where's the best coffee on campus?", icon: '☕' },
  { text: 'How do I register for classes?', icon: '📝' }
]

export default function PromptPage({ onSubmit }: PromptPageProps) {
  const [prompt, setPrompt] = useState('')
  const trimmedPrompt = prompt.trim()
  const isEnabled = trimmedPrompt.length > 0

  return (
    <div className="relative min-h-screen overflow-y-auto px-4 py-10 pb-16 text-white">
      <div className="fixed inset-0 bg-gradient-to-br from-[#001f3f] via-[#0a0a0a] to-[#000000]" />
      <div
        className="fixed inset-0 opacity-10"
        style={{
          backgroundImage:
            'radial-gradient(ellipse at 20% 20%, rgba(227, 25, 55, 0.08) 0%, transparent 50%), radial-gradient(ellipse at 80% 80%, rgba(255, 184, 28, 0.06) 0%, transparent 50%)'
        }}
      />

      <div className="relative z-10 mx-auto max-w-3xl">
        <div className="mb-12 text-center animate-in fade-in slide-in-from-top-4 duration-1000">
          <h1 className="mb-4 text-6xl font-black tracking-tight text-white sm:text-7xl">
            Welcome to{' '}
            <span className="bg-gradient-to-r from-[#E31937] to-[#FFB81C] bg-clip-text text-transparent">
              CampusPilot
            </span>
          </h1>
          <p className="mx-auto max-w-2xl text-xl font-light leading-relaxed text-gray-300">
            Ask anything about campus and your AI agents will find the answers in seconds.
          </p>
        </div>

        <div className="overflow-hidden rounded-3xl animate-in fade-in slide-in-from-bottom-4 duration-1000 delay-300">
          <div className="rounded-3xl bg-[#1a1a1a]/90 p-8 shadow-2xl border border-[#E31937]/20 shadow-red-500/10 backdrop-blur-2xl">
            <div className="flex flex-col gap-6">
              <div className="space-y-6">
                <p className="text-center text-sm font-medium uppercase tracking-wider text-gray-400">
                  Try asking
                </p>
                <div className="grid grid-cols-2 gap-3">
                  {suggestionChips.map(({ text, icon }) => (
                    <button
                      key={text}
                      onClick={() => setPrompt(text)}
                      className="group inline-flex items-center gap-3 rounded-full border border-[#FFB81C]/20 bg-[#FFB81C]/8 px-5 py-3 text-left backdrop-blur-sm transition-all duration-300 hover:scale-105 hover:border-[#FFB81C]/40 hover:bg-[#FFB81C]/15 hover:shadow-lg hover:shadow-yellow-400/20"
                    >
                      <span className="shrink-0 text-lg transition-transform duration-200 group-hover:scale-110">
                        {icon}
                      </span>
                      <span className="text-sm font-medium text-[#FFB81C] group-hover:text-yellow-200">
                        {text}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="group relative animate-in fade-in slide-in-from-bottom-4 duration-1000 delay-500">
                <div className="pointer-events-none absolute inset-0 rounded-2xl bg-gradient-to-r from-[#E31937] via-[#FFB81C] to-[#E31937] opacity-0 blur-2xl transition-all duration-500 group-focus-within:opacity-20" />
                <div className="relative rounded-2xl border border-gray-700/30 bg-[#0a0a0a]/95 shadow-2xl shadow-black/40 transition-all duration-500 group-focus-within:border-[#E31937]/40">
                  <textarea
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && e.ctrlKey && isEnabled) {
                        onSubmit(trimmedPrompt)
                      }
                    }}
                    placeholder="What would you like to know about campus?"
                    className="min-h-32 max-h-56 w-full resize-none rounded-2xl bg-transparent p-8 text-lg font-light leading-relaxed text-white outline-none placeholder:text-gray-400"
                  />
                </div>
              </div>

              <button
                onClick={() => onSubmit(trimmedPrompt)}
                disabled={!isEnabled}
                className={`w-full rounded-2xl px-8 py-5 text-lg font-bold transition-all duration-500 animate-in fade-in slide-in-from-bottom-4 delay-700 ${
                  isEnabled
                    ? 'bg-gradient-to-r from-[#E31937] via-[#FFB81C] to-[#E31937] text-white shadow-2xl shadow-red-500/40 hover:scale-[1.02] hover:from-[#E31937]/90 hover:via-[#FFB81C]/90 hover:to-[#E31937]/90'
                    : 'cursor-not-allowed border border-gray-700/30 bg-gray-800/50 text-gray-500'
                }`}
              >
                {isEnabled ? 'Run agents' : 'Enter your question'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
