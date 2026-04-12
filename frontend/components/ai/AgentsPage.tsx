'use client'

import { QueryResponse } from '@/lib/types'

interface LiveStage {
  name: string
  status: string
  description: string
  detail?: string
  completionMessage?: string
  steps: { title: string; status: 'running' | 'completed' | 'failed' | 'queued'; message: string }[]
}

interface AgentsPageProps {
  query: string
  stages: LiveStage[]
  response: QueryResponse | null
  revealed: boolean
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

export default function AgentsPage({ query, stages, response, revealed, onRevealSummary, onReset, statusLabel }: AgentsPageProps) {
  const visibleStages = stages.filter((stage) => ['Queued', 'Running', 'Completed', 'Attention'].includes(stage.status))
  const summaryTitle = response?.presentation?.summary?.title || 'TerpAI completed the workflow and returned the result below.'
  const workflowComplete = Boolean(response) && !statusLabel?.toLowerCase().includes('error')

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
    <div className="relative min-h-screen overflow-hidden bg-[#F8FAFC] px-4 py-10 text-[#111827]">
      <div className="absolute top-20 right-10 h-96 w-96 rounded-full bg-[#FFB81C]/5 blur-3xl" />
      <div className="absolute bottom-40 left-20 h-80 w-80 rounded-full bg-[#E31937]/5 blur-3xl" />

      <div className="relative mx-auto w-full max-w-6xl space-y-8">
        <div className="rounded-[36px] border border-[#E31937]/10 bg-white/95 p-8 shadow-[0_30px_90px_-40px_rgba(227,25,55,0.35)] backdrop-blur-xl">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
            <div className="space-y-3">
              <p className="text-sm uppercase tracking-[0.3em] text-[#92400E]">Agent launch pad</p>
              <h2 className="text-4xl font-black">Campus AI agents are running</h2>
              <p className="max-w-2xl text-base leading-7 text-[#475569]">
                The task planner runs first, then only the selected agents appear here, and finally the aggregator completes the response.
              </p>
            </div>
            <div className="rounded-3xl bg-[#FFB81C] px-6 py-5 text-white shadow-xl shadow-[#E31937]/20">
              <p className="text-sm uppercase tracking-[0.3em]">Current query</p>
              <p className="mt-4 text-xl font-semibold">{query}</p>
              {statusLabel && <p className="mt-2 text-sm text-white/90">{statusLabel}</p>}
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-[32px] border border-[#E31937]/10 bg-white p-6 shadow-sm">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="text-sm uppercase tracking-[0.3em] text-[#92400E]">Live workflow</p>
                <h3 className="mt-2 text-2xl font-bold text-[#111827]">Task planner first, selected agents second, aggregator last</h3>
                <p className="mt-2 text-sm text-[#475569]">
                  Each card updates as live websocket events arrive from the backend.
                </p>
              </div>
              <div className="rounded-2xl bg-[#F8FAFC] px-4 py-3 text-sm text-[#475569]">
                {visibleStages.length} live stage{visibleStages.length === 1 ? '' : 's'} visible
              </div>
            </div>

            <div className="mt-6 space-y-4">
              {visibleStages.map((stage) => (
                <div key={stage.name} className="rounded-[28px] border border-[#E5E7EB] bg-[#FFFBEB] p-5">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <p className="text-xs uppercase tracking-[0.3em] text-[#92400E]">{stage.name}</p>
                      <p className="mt-2 text-lg font-semibold text-[#111827]">{stage.description}</p>
                      <p className="mt-2 text-sm text-[#475569]">{stage.status === 'Completed' ? stage.completionMessage || stage.detail || 'Completed.' : stage.detail || 'Waiting for live update...'}</p>
                    </div>
                    <span className={`inline-flex w-fit rounded-full px-3 py-1 text-sm font-semibold ${agentColors[stage.status] || agentColors.Waiting}`}>
                      {stage.status}
                    </span>
                  </div>

                  {(() => {
                    const currentStep = pickCurrentStep(stage)
                    const currentStepIndex = currentStep ? Math.max(0, stage.steps.findIndex((step) => step.title === currentStep.title && step.status === currentStep.status)) : -1
                    return (
                      <div className="mt-4 rounded-2xl border border-[#E5E7EB] bg-white p-4">
                        {currentStep ? (
                          <div className="rounded-xl bg-[#F8FAFC] px-3 py-3">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <p className="text-sm font-semibold text-[#111827]">
                                Step {currentStepIndex >= 0 ? currentStepIndex + 1 : 1}: {currentStep.title}
                              </p>
                              <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${stepBadgeClass(currentStep.status)}`}>
                                {normalizeStepLabel(currentStep.status)}
                              </span>
                            </div>
                            <p className="mt-2 text-xs leading-6 text-[#475569]">{currentStep.message}</p>
                          </div>
                        ) : (
                          <div className="rounded-xl bg-[#F8FAFC] px-3 py-3">
                            <p className="text-sm font-semibold text-[#111827]">No step details available yet.</p>
                          </div>
                        )}
                      </div>
                    )
                  })()}

                  <div className="mt-4 h-2 overflow-hidden rounded-full bg-[#F3F4F6]">
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
                      style={{
                        width:
                          stage.status === 'Completed' ? '100%' : stage.status === 'Running' ? '68%' : stage.status === 'Attention' ? '48%' : '18%',
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-[32px] border border-[#E31937]/10 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm uppercase tracking-[0.3em] text-[#92400E]">Aggregator summary</p>
                <h3 className="mt-2 text-2xl font-bold text-[#111827]">{summaryTitle}</h3>
              </div>
              {workflowComplete && (
                <button
                  onClick={onRevealSummary}
                  className="inline-flex items-center justify-center rounded-[28px] bg-[#E31937] px-6 py-3 text-sm font-semibold text-white transition hover:bg-[#c61631]"
                >
                  {revealed ? 'Report opened' : 'Open final report'}
                </button>
              )}
            </div>

            {revealed && response && (
              <div className="mt-6 space-y-6">
                <div className="rounded-[28px] border border-[#E5E7EB] bg-[#0F172A] p-5 shadow-sm">
                  <p className="text-sm uppercase tracking-[0.25em] text-[#93C5FD]">Aggregator payload (raw)</p>
                  <pre className="mt-4 max-h-[60vh] overflow-auto whitespace-pre-wrap break-words rounded-2xl bg-[#111827] p-4 text-xs leading-6 text-[#E5E7EB]">
                    {JSON.stringify(response, null, 2)}
                  </pre>
                </div>

                <div className="flex justify-end">
                  <button
                    onClick={onReset}
                    className="inline-flex items-center justify-center rounded-[28px] border border-[#E31937] bg-white px-6 py-3 text-sm font-semibold text-[#E31937] transition hover:bg-[#FEF2F2]"
                  >
                    Start another query
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}