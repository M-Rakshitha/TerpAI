'use client'

import { QueryResponse } from '@/lib/types'

interface LiveStage {
  name: string
  status: string
  description: string
  detail?: string
  completionMessage?: string
  progress?: number
  currentStep?: number
  totalSteps?: number
  activity?: string
  lastUpdatedAt?: string
  steps: { title: string; status: 'running' | 'completed' | 'failed' | 'queued'; message: string; stepNumber?: number }[]
}

interface AgentsPageProps {
  query: string
  stages: LiveStage[]
  response: QueryResponse | null
  onRevealSummary: () => void
  onReset: () => void
  statusLabel?: string
}

const agentColors: Record<string, string> = {
  Initializing: 'bg-[#FEF3C7] text-[#7A5A00]',
  Running: 'bg-[#FFE7EB] text-[#C8102E]',
  Waiting: 'bg-[#E5E7EB] text-[#374151]',
  Completed: 'bg-[#FFF8CC] text-[#7A5A00]',
  Attention: 'bg-[#FEE2E2] text-[#991B1B]',
  Queued: 'bg-[#E5E7EB] text-[#374151]',
}

export default function AgentsPage({ query, stages, response, onRevealSummary, onReset, statusLabel }: AgentsPageProps) {
  const visibleStages = stages
    .filter((stage) => ['Queued', 'Running', 'Completed', 'Attention'].includes(stage.status))
    .reduce<LiveStage[]>((acc, stage) => {
      const key = stage.name.trim().toLowerCase()
      const existingIndex = acc.findIndex((item) => item.name.trim().toLowerCase() === key)
      if (existingIndex === -1) {
        acc.push(stage)
        return acc
      }

      const existing = acc[existingIndex]
      const existingTs = existing.lastUpdatedAt ? Date.parse(existing.lastUpdatedAt) : 0
      const currentTs = stage.lastUpdatedAt ? Date.parse(stage.lastUpdatedAt) : 0
      if (currentTs >= existingTs) {
        acc[existingIndex] = stage
      }
      return acc
    }, [])

  const activatedAgents = Array.from(new Set(visibleStages
    .filter((stage) => !['Task Planner', 'Aggregator'].includes(stage.name))
    .map((stage) => stage.name.trim().toLowerCase())))
  const summaryTitle = response?.presentation?.summary?.title || 'TerpAI completed the workflow and returned the result below.'
  const workflowComplete = Boolean(response) && !response?.awaiting_user_input && !statusLabel?.toLowerCase().includes('error')
  const runningCount = visibleStages.filter((stage) => stage.status === 'Running').length
  const queuedCount = visibleStages.filter((stage) => stage.status === 'Queued').length
  const completedCount = visibleStages.filter((stage) => stage.status === 'Completed').length
  const attentionCount = visibleStages.filter((stage) => stage.status === 'Attention').length

  const stageProgress = (stage: LiveStage) => {
    if (typeof stage.progress === 'number') {
      return Math.max(3, Math.min(100, stage.progress))
    }
    if (stage.status === 'Completed') return 100
    if (stage.status === 'Running') return 20
    if (stage.status === 'Attention') return 100
    return 8
  }

  const progressSegments = (stage: LiveStage, segments = 6) => {
    const progress = stageProgress(stage)
    const activeCount = Math.max(1, Math.round((progress / 100) * segments))
    return Array.from({ length: segments }, (_, idx) => idx < activeCount)
  }

  const agentPill = (name: string) =>
    name
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (char) => char.toUpperCase())

  const pickCurrentStep = (stage: LiveStage): { title: string; status: 'running' | 'completed' | 'failed' | 'queued'; message: string } | null => {
    if (!stage.steps || stage.steps.length === 0) return null

    if (stage.status === 'Completed') {
      const last = [...stage.steps].reverse().find((step) => step.status === 'completed') || stage.steps[stage.steps.length - 1]
      return {
        title: last.title,
        status: 'completed',
        message: stage.completionMessage || stage.detail || 'All steps completed.',
      }
    }

    if (stage.status === 'Attention') {
      return stage.steps.find((step) => step.status === 'failed') || stage.steps[0]
    }

    return (
      stage.steps.find((step) => step.status === 'running') ||
      stage.steps.find((step) => step.status === 'queued') ||
      stage.steps[stage.steps.length - 1]
    )
  }

  const stageHeadline = (stage: LiveStage) => {
    if (stage.detail) return stage.detail
    const currentStep = pickCurrentStep(stage)
    if (currentStep?.message) return currentStep.message
    if (stage.status === 'Completed') return stage.completionMessage || 'Workflow completed successfully.'
    return 'Waiting for live update...'
  }

  return (
    <div className="relative min-h-screen overflow-hidden px-4 py-10 text-white">
      <div className="fixed inset-0 bg-gradient-to-br from-[#001f3f] via-[#0a0a0a] to-[#000000]" />
      <div
        className="fixed inset-0 opacity-10"
        style={{
          backgroundImage:
            'radial-gradient(ellipse at 20% 20%, rgba(227, 25, 55, 0.08) 0%, transparent 50%), radial-gradient(ellipse at 80% 80%, rgba(255, 184, 28, 0.06) 0%, transparent 50%)'
        }}
      />

      <div className="relative mx-auto w-full max-w-6xl space-y-8">
        <div className="rounded-[36px] border border-[#E31937]/20 bg-[#1a1a1a]/90 p-8 shadow-2xl shadow-red-500/10 backdrop-blur-2xl">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
            <div className="space-y-3">
              <p className="text-sm uppercase tracking-[0.3em] text-[#FFB81C]">Agent launch pad</p>
              <h2 className="text-4xl font-black text-white">Campus AI agents are running</h2>
              <p className="max-w-2xl text-base leading-7 text-gray-300">
                The task planner runs first, then only the selected agents appear here, and finally the aggregator completes the response.
              </p>
            </div>
            <div className="rounded-3xl border border-[#FFB81C]/20 bg-[#111827] px-6 py-5 text-white shadow-xl shadow-black/30">
              <p className="text-sm uppercase tracking-[0.3em]">Current query</p>
              <p className="mt-4 text-xl font-semibold text-[#FDE68A]">{query}</p>
              {statusLabel && <p className="mt-2 text-sm text-white/90">{statusLabel}</p>}
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-[32px] border border-[#E31937]/20 bg-[#1a1a1a]/90 p-6 shadow-2xl shadow-black/20">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="text-sm uppercase tracking-[0.3em] text-[#FFD200]">Live workflow</p>
                <h3 className="mt-2 text-2xl font-bold text-white">From intent to answers, in one continuous stream</h3>
                <p className="mt-2 text-sm text-gray-300">
                  We orchestrate planning, parallel agent execution, and final synthesis with real-time updates.
                </p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-[#111827] px-4 py-3 text-xs uppercase tracking-[0.18em] text-gray-300">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#22C55E]" />{runningCount} running</span>
                  <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#9CA3AF]" />{queuedCount} queued</span>
                  <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#16A34A]" />{completedCount} done</span>
                  {attentionCount > 0 && <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#DC2626]" />{attentionCount} attention</span>}
                </div>
              </div>
            </div>

            <div className="mt-6 space-y-4">
              {activatedAgents.length > 0 && (
                <div className="rounded-2xl border border-white/10 bg-[#0f0f0f] p-4">
                  <p className="text-xs uppercase tracking-[0.25em] text-[#FFD200]">Triggered agents</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {activatedAgents.map((agent) => {
                      const stage = visibleStages.find((item) => item.name.trim().toLowerCase() === agent)
                      const running = stage?.status === 'Running'
                      return (
                        <span
                          key={agent}
                          className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-[#111827] px-3 py-1 text-xs font-semibold text-gray-200"
                        >
                          <span className={`h-2 w-2 rounded-full ${running ? 'animate-pulse bg-[#C8102E]' : stage?.status === 'Completed' ? 'bg-[#FFD200]' : stage?.status === 'Attention' ? 'bg-[#DC2626]' : 'bg-[#9CA3AF]'}`} />
                          {agentPill(agent)}
                        </span>
                      )
                    })}
                  </div>
                </div>
              )}

              {visibleStages.map((stage) => (
                <div key={stage.name} className="rounded-[28px] border border-[#FFB81C]/15 bg-[#111827] p-5">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <p className="text-xs uppercase tracking-[0.3em] text-[#FFD200]">{agentPill(stage.name)}</p>
                      <p className="mt-2 text-lg font-semibold text-white">{stage.description}</p>
                      <p className="mt-2 text-sm text-gray-300">{stageHeadline(stage)}</p>
                    </div>
                    <span className={`inline-flex w-fit items-center gap-2 rounded-full px-3 py-1 text-sm font-semibold ${agentColors[stage.status] || agentColors.Waiting}`}>
                      {stage.status === 'Running' && <span className="h-2 w-2 animate-pulse rounded-full bg-[#C8102E]" />}
                      {stage.status}
                    </span>
                  </div>

                  <div className="mt-4">
                    <div className="rounded-xl border border-white/10 bg-[#0f0f0f] px-3 py-2">
                      <div className="flex items-center gap-2">
                        {progressSegments(stage).map((active, idx) => (
                          <span
                            key={`${stage.name}-segment-${idx}`}
                            className={`h-1.5 flex-1 rounded-full transition-all duration-500 ${
                              active
                                ? stage.status === 'Attention'
                                  ? 'bg-[#DC2626]'
                                  : stage.status === 'Completed'
                                    ? 'bg-[#FFD200]'
                                    : 'animate-pulse bg-[#C8102E]'
                                : 'bg-white/10'
                            }`}
                          />
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-[32px] border border-[#E31937]/20 bg-[#1a1a1a]/90 p-6 shadow-2xl shadow-black/20">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm uppercase tracking-[0.3em] text-[#FFB81C]">Aggregator summary</p>
                <h3 className="mt-2 text-2xl font-bold text-white">{summaryTitle}</h3>
              </div>
              {workflowComplete && (
                <button
                  onClick={onRevealSummary}
                  className="inline-flex items-center justify-center rounded-[28px] border border-[#F59E0B]/40 bg-[#111827] px-6 py-3 text-sm font-semibold text-[#FDE68A] shadow-lg shadow-black/30 transition hover:border-[#FBBF24] hover:bg-[#1f2937] hover:text-[#FEF3C7]"
                >
                  View polished report
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
