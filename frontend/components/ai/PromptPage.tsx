'use client'

import { useState } from 'react'

interface PromptPageProps {
  onSubmit: (prompt: string) => void
}

export default function PromptPage({ onSubmit }: PromptPageProps) {
  const [prompt, setPrompt] = useState('')
  const trimmedPrompt = prompt.trim()
  const isEnabled = trimmedPrompt.length > 0

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#f8fafc] to-[#f0f9ff] px-4 py-20">
      <div className="mx-auto max-w-3xl">
        {/* Header */}
        <div className="mb-12 text-center">
          <div className="inline-block rounded-full bg-[#E31937]/10 px-4 py-2 mb-4">
            <p className="text-sm font-semibold text-[#E31937] uppercase tracking-wide">UMD College Park</p>
          </div>
          <h1 className="text-5xl font-black text-[#111827] mb-4">
            Welcome to <span className="bg-gradient-to-r from-[#E31937] to-[#FFB81C] bg-clip-text text-transparent">TerpAI</span>
          </h1>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            Ask your campus questions and watch AI agents work in parallel to find you answers.
          </p>
        </div>

        {/* Main card */}
        <div className="rounded-2xl border border-[#E31937]/10 bg-white shadow-xl overflow-hidden">
          {/* Top accent bar */}
          <div className="h-1 bg-gradient-to-r from-[#E31937] to-[#FFB81C]"></div>
          
          <div className="p-8 space-y-6">
            {/* Quick suggestions */}
            <div className="space-y-2">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Try asking about</p>
              <div className="flex flex-wrap gap-2">
                {['Dining options', 'Study spots', 'Class schedule', 'Campus routes'].map((tag) => (
                  <button
                    key={tag}
                    onClick={() => setPrompt(tag)}
                    className="rounded-full border border-[#FFB81C]/30 bg-[#FFB81C]/5 px-4 py-2 text-sm font-medium text-[#92400E] hover:bg-[#FFB81C]/10 transition"
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>

            {/* Text input */}
            <div className="space-y-2">
              <label className="block text-sm font-semibold text-[#111827]">
                Your Question
              </label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Where is the nearest Chick-fil-A? How do I get to the library? What events are happening today?"
                className="w-full min-h-32 p-4 border-2 border-gray-200 rounded-lg focus:border-[#E31937] focus:ring-2 focus:ring-[#E31937]/20 outline-none transition text-base text-[#111827] placeholder-gray-400"
              />
            </div>

            {/* Submit button */}
            <button
              onClick={() => onSubmit(trimmedPrompt)}
              disabled={!isEnabled}
              className={`w-full font-bold py-4 px-6 rounded-lg transition-all duration-200 transform ${
                isEnabled
                  ? 'bg-gradient-to-r from-[#E31937] to-[#FFB81C] text-white hover:shadow-lg hover:scale-105 active:scale-95 cursor-pointer'
                  : 'bg-gray-300 text-gray-500 cursor-not-allowed'
              }`}
            >
              {isEnabled ? '🚀 Run Agents' : '✏️ Enter a question to start'}
            </button>

            {/* Info footer */}
            <div className="bg-[#F8FAFC] rounded-lg p-4 text-sm text-gray-600 text-center border border-gray-200">
              <p>
                <strong className="text-[#E31937]">How it works:</strong> Your question gets split into tasks for parallel AI agents (Search, Location, Insights) that work together to give you the best answer.
              </p>
            </div>
          </div>
        </div>

        {/* Feature cards */}
        <div className="mt-12 grid md:grid-cols-3 gap-4">
          {[
            { icon: '🔍', title: 'Smart Search', desc: 'Intelligent queries' },
            { icon: '📍', title: 'Location Aware', desc: 'UMD context' },
            { icon: '⚡', title: 'Real-time AI', desc: 'Parallel agents' },
          ].map((feature) => (
            <div key={feature.title} className="rounded-lg bg-white/50 backdrop-blur border border-white p-4 text-center hover:shadow-md transition">
              <div className="text-2xl mb-2">{feature.icon}</div>
              <h3 className="font-semibold text-[#111827]">{feature.title}</h3>
              <p className="text-xs text-gray-500">{feature.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
