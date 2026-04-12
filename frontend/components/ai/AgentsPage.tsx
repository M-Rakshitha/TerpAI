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
  steps: { title: string; status: 'running' | 'completed' | 'failed' | 'queued'; message: string }[]
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
  Initializing: 'bg-[#FEF3C7] text-[#92400E]',
  Running: 'bg-[#DDEBF9] text-[#1D4ED8]',
  Waiting: 'bg-[#E5E7EB] text-[#374151]',
  Completed: 'bg-[#DCFCE7] text-[#166534]',
  Attention: 'bg-[#FEE2E2] text-[#991B1B]',
  Queued: 'bg-[#E5E7EB] text-[#374151]',
}

export default function AgentsPage({ query, stages, response, onRevealSummary, onReset, statusLabel }: AgentsPageProps) {
  const visibleStages = stages.filter((stage) => ['Queued', 'Running', 'Completed', 'Attention'].includes(stage.status))
  const summaryTitle = response?.presentation?.summary?.title || 'TerpAI completed the workflow and returned the result below.'
  const workflowComplete = Boolean(response) && !response?.awaiting_user_input && !statusLabel?.toLowerCase().includes('error')

  const stepBadgeClass = (status: 'running' | 'completed' | 'failed' | 'queued') => {
    if (status === 'completed') return 'bg-[#DCFCE7] text-[#166534]'
    if (status === 'running') return 'bg-[#DBEAFE] text-[#1D4ED8]'
    if (status === 'failed') return 'bg-[#FEE2E2] text-[#991B1B]'
    return 'bg-[#E5E7EB] text-[#374151]'
  }

  const normalizeStepLabel = (status: 'running' | 'completed' | 'failed' | 'queued') => {
    if (status === 'running') return 'Running'
    if (status === 'completed') return 'Completed'
    if (status === 'failed') return 'Needs attention'
    return 'Queued'
  }

  const stageProgress = (stage: LiveStage) => {
    if (typeof stage.progress === 'number') {
      return Math.max(3, Math.min(100, stage.progress))
    }
    if (stage.status === 'Completed') return 100
    if (stage.status === 'Running') return 20
    if (stage.status === 'Attention') return 100
    return 8
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
              <p className="mt-4 text-xl font-semibold">{query}</p>
              {statusLabel && <p className="mt-2 text-sm text-white/90">{statusLabel}</p>}
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-[32px] border border-[#E31937]/20 bg-[#1a1a1a]/90 p-6 shadow-2xl shadow-black/20">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="text-sm uppercase tracking-[0.3em] text-[#FFB81C]">Live workflow</p>
                <h3 className="mt-2 text-2xl font-bold text-white">Task planner first, selected agents second, aggregator last</h3>
                <p className="mt-2 text-sm text-gray-300">
                  Each card updates as live websocket events arrive from the backend.
                </p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-[#111827] px-4 py-3 text-sm text-gray-300">
                {visibleStages.length} live stage{visibleStages.length === 1 ? '' : 's'} visible
              </div>
            </div>

            <div className="mt-6 space-y-4">
              {visibleStages.map((stage) => (
                <div key={stage.name} className="rounded-[28px] border border-[#FFB81C]/15 bg-[#111827] p-5">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <p className="text-xs uppercase tracking-[0.3em] text-[#FFB81C]">{agentPill(stage.name)}</p>
                      <p className="mt-2 text-lg font-semibold text-white">{stage.description}</p>
                      <p className="mt-2 text-sm text-gray-300">{stage.status === 'Completed' ? stage.completionMessage || stage.detail || 'Completed.' : stage.detail || 'Waiting for live update...'}</p>
                    </div>
                    <span className={`inline-flex w-fit rounded-full px-3 py-1 text-sm font-semibold ${agentColors[stage.status] || agentColors.Waiting}`}>
                      {stage.status}
                    </span>
                  </div>

                  {(() => {
                    const currentStep = pickCurrentStep(stage)
                    const currentStepIndex = currentStep ? Math.max(0, stage.steps.findIndex((step) => step.title === currentStep.title && step.status === currentStep.status)) : -1
                    return (
                      <div className="mt-4 rounded-2xl border border-white/10 bg-[#1a1a1a] p-4">
                        {currentStep ? (
                          <div className="rounded-xl bg-[#0f0f0f] px-3 py-3">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <p className="text-sm font-semibold text-white">{stage.activity || currentStep.title}</p>
                              <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${stepBadgeClass(currentStep.status)}`}>
                                {normalizeStepLabel(currentStep.status)}
                              </span>
                            </div>
                            <p className="mt-2 text-xs leading-6 text-gray-300">{currentStep.message}</p>
                          </div>
                        ) : (
                          <div className="rounded-xl bg-[#0f0f0f] px-3 py-3">
                            <p className="text-sm font-semibold text-white">No step details available yet.</p>
                          </div>
                        )}
                      </div>
                    )
                  })()}

                  <div className="mt-4 space-y-2">
                    <div className="h-2 overflow-hidden rounded-full bg-white/10">
                      <div
                        className={`h-full rounded-full transition-all duration-700 ${
                          stage.status === 'Completed'
                            ? 'bg-[#16A34A]'
                            : stage.status === 'Running'
                              ? 'bg-[#2563EB]'
                              : stage.status === 'Attention'
                                ? 'bg-[#DC2626]'
                                : 'bg-[#9CA3AF]'
                        }`}
                        style={{ width: `${stageProgress(stage)}%` }}
                      />
                    </div>
                    <div
                      className="flex items-center justify-between rounded-xl border border-white/10 bg-[#0f0f0f] px-3 py-2 text-[11px] uppercase tracking-[0.2em] text-gray-400"
                    >
                      <span>{stage.status === 'Running' ? 'Live stream' : 'Stage state'}</span>
                      <span>{stage.currentStep && stage.totalSteps ? `${stage.currentStep}/${stage.totalSteps}` : `${Math.round(stageProgress(stage))}%`}</span>
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
                  className="inline-flex items-center justify-center rounded-[28px] bg-gradient-to-r from-[#E31937] via-[#FFB81C] to-[#E31937] px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-red-500/20 transition hover:scale-[1.02]"
                >
                  Open final report
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
