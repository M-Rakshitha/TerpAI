'use client'

import Dashboard from '@/components/dashboard/Dashboard'
import {
  QueryResponse,
  QueryVisualChart,
  QueryVisualMetric,
} from '@/lib/types'
import {
  Bar,
  BarChart,
  Cell,
  CartesianGrid,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

interface ResultsPageProps {
  prompt: string
  response: QueryResponse | null
  revealed: boolean
  onReveal: () => void
  onReset: () => void
}

function formatEventLabel(eventType?: string, status?: string) {
  if (eventType === 'planner_status') {
    return status === 'completed' ? 'Planner completed' : 'Planner running'
  }

  if (eventType === 'agent_status') {
    return status ? `${status[0].toUpperCase()}${status.slice(1)}` : 'Agent update'
  }

  return eventType || 'Update'
}

const metricToneStyles: Record<string, string> = {
  accent: 'bg-[#FFFBEB] text-[#92400E] border-[#FCD34D]',
  success: 'bg-[#ECFDF5] text-[#166534] border-[#86EFAC]',
  warning: 'bg-[#FFF7ED] text-[#9A3412] border-[#FDBA74]',
  neutral: 'bg-[#F8FAFC] text-[#334155] border-[#E2E8F0]',
}

const chartColors = ['#E31937', '#FFB81C', '#1D4ED8', '#16A34A', '#0F172A', '#7C3AED']

function formatMetricValue(metric: QueryVisualMetric) {
  const rawValue = metric.value ?? 0
  const suffix = metric.suffix ? ` ${metric.suffix}` : ''
  return `${rawValue}${suffix}`
}

function renderChart(chart: QueryVisualChart) {
  const chartData = Array.isArray(chart.data) ? chart.data : []
  const palette = chart.colors && chart.colors.length > 0 ? chart.colors : chartColors

  if (chart.kind === 'pie') {
    return (
      <ResponsiveContainer width="100%" height={240}>
        <PieChart>
          <Pie data={chartData} dataKey="value" nameKey="label" cx="50%" cy="50%" outerRadius={80} innerRadius={48} paddingAngle={4}>
            {chartData.map((entry, index) => (
              <Cell key={`${chart.id || 'pie'}-${entry.label || index}`} fill={entry.color || palette[index % palette.length]} />
            ))}
          </Pie>
          <Tooltip />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
        <XAxis dataKey="label" tickLine={false} axisLine={false} fontSize={12} />
        <YAxis tickLine={false} axisLine={false} fontSize={12} />
        <Tooltip />
        <Bar dataKey="value" radius={[12, 12, 0, 0]}>
          {chartData.map((entry, index) => (
            <Cell key={`${chart.id || 'bar'}-${entry.label || index}`} fill={entry.color || palette[index % palette.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export default function ResultsPage({ prompt, response, revealed, onReveal, onReset }: ResultsPageProps) {
  const highlights = response?.presentation?.summary?.highlights || []
  const quickActions = response?.presentation?.quick_actions || []
  const timeline = response?.agent_execution?.timeline || []
  const summary = response?.presentation?.summary
  const summaryTitle = summary?.title || 'TerpAI completed the workflow and returned the result below.'
  const visualReport = response?.presentation?.visual_report
  const visualMetrics = visualReport?.metrics || []
  const visualCharts = visualReport?.charts || []
  const storyPoints = visualReport?.story_points || highlights

  if (!revealed) {
    return (
      <div className="relative min-h-screen overflow-hidden bg-[#F8FAFC] px-4 py-10 text-[#111827]">
        <div className="absolute top-0 right-0 -mr-32 -mt-32 h-72 w-72 rounded-full bg-[#E31937]/8 blur-3xl" />
        <div className="absolute bottom-0 left-0 -ml-40 -mb-40 h-80 w-80 rounded-full bg-[#FFB81C]/8 blur-3xl" />

        <div className="relative mx-auto w-full max-w-4xl space-y-8">
          <div className="rounded-[36px] border border-[#E31937]/10 bg-white/95 p-8 shadow-[0_35px_100px_-45px_rgba(227,25,55,0.3)] backdrop-blur-xl">
            <div className="space-y-4 text-center">
              <p className="text-sm uppercase tracking-[0.28em] text-[#92400E]">Workflow complete</p>
              <h2 className="text-4xl font-black">Aggregator summary is ready</h2>
              <p className="mx-auto max-w-2xl text-base leading-7 text-[#475569]">
                The task planner, selected agents, and aggregator have all finished. Open the final report to see the synthesized visual output.
              </p>
            </div>

            <div className="mt-10 grid gap-6 md:grid-cols-3">
              <div className="rounded-[28px] border border-[#E31937]/10 bg-[#FFFBEB] p-6 shadow-sm">
                <p className="text-xs uppercase tracking-[0.3em] text-[#92400E]">Prompt</p>
                <p className="mt-3 text-base font-semibold text-[#111827]">{prompt}</p>
              </div>
              <div className="rounded-[28px] border border-[#E31937]/10 bg-white p-6 shadow-sm md:col-span-2">
                <p className="text-xs uppercase tracking-[0.3em] text-[#475569]">Backend ready</p>
                <p className="mt-3 text-base leading-7 text-[#111827]">{summaryTitle}</p>
                <p className="mt-3 text-sm text-[#475569]">
                  The report page will surface the metrics, charts, and result cards generated by the backend.
                </p>
              </div>
            </div>

            <div className="mt-10 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-center">
              <button
                onClick={onReveal}
                className="inline-flex items-center justify-center rounded-[28px] bg-[#E31937] px-6 py-3 text-sm font-semibold text-white transition hover:bg-[#c61631]"
              >
                Open final report
              </button>
              <button
                onClick={onReset}
                className="inline-flex items-center justify-center rounded-[28px] border border-[#E31937] bg-white px-6 py-3 text-sm font-semibold text-[#E31937] transition hover:bg-[#FEF2F2]"
              >
                Start another query
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#F8FAFC] px-4 py-10 text-[#111827]">
      <div className="absolute top-0 right-0 -mr-32 -mt-32 h-72 w-72 rounded-full bg-[#E31937]/8 blur-3xl" />
      <div className="absolute bottom-0 left-0 -ml-40 -mb-40 h-80 w-80 rounded-full bg-[#FFB81C]/8 blur-3xl" />

      <div className="relative mx-auto w-full max-w-6xl space-y-8">
        <div className="rounded-[36px] border border-[#E31937]/10 bg-white/95 p-8 shadow-[0_35px_100px_-45px_rgba(227,25,55,0.3)] backdrop-blur-xl">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm uppercase tracking-[0.28em] text-[#92400E]">Final campus answer</p>
              <h2 className="mt-2 text-4xl font-black">{visualReport?.headline || 'Aggregated Results'}</h2>
              <p className="mt-3 max-w-2xl text-base leading-7 text-[#475569]">
                {visualReport?.subheadline || 'The backend ran the requested agents, aggregated their outputs, and returned the final student-ready result.'}
              </p>
            </div>
            <button
              onClick={onReset}
              className="inline-flex items-center justify-center rounded-[28px] border border-[#E31937] bg-white px-6 py-3 text-sm font-semibold text-[#E31937] transition hover:bg-[#FEF2F2]"
            >
              Ask another question
            </button>
          </div>

          <div className="mt-10 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {visualMetrics.length > 0
              ? visualMetrics.map((metric, index) => (
                  <div key={`${metric.label || 'metric'}-${index}`} className={`rounded-[28px] border p-5 shadow-sm ${metricToneStyles[metric.tone || 'neutral'] || metricToneStyles.neutral}`}>
                    <p className="text-xs uppercase tracking-[0.3em] opacity-80">{metric.label || 'Metric'}</p>
                    <p className="mt-4 text-3xl font-black">{formatMetricValue(metric)}</p>
                  </div>
                ))
              : [
                  { label: 'Activated agents', value: response?.agents_used?.length || 0, suffix: 'agents', tone: 'accent' },
                  { label: 'Highlights', value: highlights.length, suffix: 'notes', tone: 'success' },
                  { label: 'Quick actions', value: quickActions.length, suffix: 'links', tone: 'warning' },
                  { label: 'Trace events', value: timeline.length, suffix: 'updates', tone: 'neutral' },
                ].map((metric, index) => (
                  <div key={`${metric.label || 'metric'}-${index}`} className={`rounded-[28px] border p-5 shadow-sm ${metricToneStyles[metric.tone || 'neutral'] || metricToneStyles.neutral}`}>
                    <p className="text-xs uppercase tracking-[0.3em] opacity-80">{metric.label || 'Metric'}</p>
                    <p className="mt-4 text-3xl font-black">{formatMetricValue(metric)}</p>
                  </div>
                ))}
          </div>

          <div className="mt-8 grid gap-6 xl:grid-cols-2">
            {visualCharts.length > 0
              ? visualCharts.map((chart, index) => (
                  <div key={`${chart.id || 'chart'}-${index}`} className="rounded-[32px] border border-[#E31937]/10 bg-white p-6 shadow-sm">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-xs uppercase tracking-[0.3em] text-[#92400E]">Visual report</p>
                        <h3 className="mt-2 text-xl font-semibold text-[#111827]">{chart.title || 'Chart'}</h3>
                      </div>
                      <span className="rounded-full bg-[#F8FAFC] px-3 py-1 text-xs font-semibold text-[#475569]">
                        {chart.kind || 'bar'}
                      </span>
                    </div>
                    <div className="mt-5">{renderChart(chart)}</div>
                  </div>
                ))
              : null}
          </div>

          <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {storyPoints.length > 0 ? (
              storyPoints.slice(0, 6).map((point, index) => (
                <div key={`${point}-${index}`} className="rounded-[28px] border border-[#E31937]/10 bg-[#FFFBEB] p-5 shadow-sm">
                  <p className="text-xs uppercase tracking-[0.3em] text-[#92400E]">Story point</p>
                  <p className="mt-3 text-sm leading-7 text-[#111827]">{point}</p>
                </div>
              ))
            ) : (
              <div className="rounded-[28px] border border-[#E31937]/10 bg-[#FFFBEB] p-5 shadow-sm md:col-span-2 xl:col-span-3">
                <p className="text-sm text-[#475569]">No highlight text was produced by the aggregator.</p>
              </div>
            )}
          </div>

          <div className="mt-8 rounded-[32px] border border-[#E31937]/10 bg-[#F8FAFC] p-5 shadow-sm">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <h3 className="text-xl font-semibold text-[#111827]">Workflow trace</h3>
              <p className="text-sm text-[#475569]">{visualReport?.section_count || response?.presentation?.sections?.length || 0} report sections prepared</p>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {timeline.slice(0, 6).map((event, index) => (
                <div key={`${event.type || 'event'}-${index}`} className="rounded-2xl border border-[#E5E7EB] bg-white p-4">
                  <p className="text-xs uppercase tracking-[0.25em] text-[#92400E]">{formatEventLabel(event.type, event.status)}</p>
                  <p className="mt-2 text-sm font-medium text-[#111827]">{event.agent || event.work || event.message || 'Backend update'}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-8 rounded-[32px] border border-[#E31937]/10 bg-white p-6 shadow-sm">
            <h3 className="text-xl font-semibold text-[#111827]">TerpAI dashboard</h3>
            <div className="mt-4 space-y-5">{response ? <Dashboard data={response} /> : <p className="text-sm text-[#475569]">Waiting for backend data...</p>}</div>

            {quickActions.length > 0 && (
              <div className="mt-8 rounded-[28px] bg-[#FFFBEB] p-5 shadow-sm">
                <p className="text-sm uppercase tracking-[0.25em] text-[#92400E]">Quick actions</p>
                <div className="mt-4 flex flex-wrap gap-3">
                  {quickActions.map((action, index) => (
                    <a
                      key={`${action.label || 'action'}-${index}`}
                      href={action.target || '#'}
                      target={action.target ? '_blank' : undefined}
                      rel={action.target ? 'noreferrer' : undefined}
                      className="rounded-full bg-white px-4 py-2 text-sm font-semibold text-[#E31937] shadow-sm transition hover:bg-[#FFF7F7]"
                    >
                      {action.label || 'Open'}
                    </a>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
