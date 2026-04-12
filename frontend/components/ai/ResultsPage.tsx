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

export default function ResultsPage({ prompt, response, onReset }: ResultsPageProps) {
  const highlights = response?.presentation?.summary?.highlights || []
  const quickActions = response?.presentation?.quick_actions || []
  const timeline = response?.agent_execution?.timeline || []
  const summary = response?.presentation?.summary
  const summaryTitle = summary?.title || 'TerpAI completed the workflow and returned the result below.'
  const visualReport = response?.presentation?.visual_report
  const visualMetrics = visualReport?.metrics || []
  const visualCharts = visualReport?.charts || []
  const storyPoints = visualReport?.story_points || highlights

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
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm uppercase tracking-[0.28em] text-[#FFB81C]">Final campus answer</p>
              <h2 className="mt-2 text-4xl font-black text-white">{visualReport?.headline || 'Aggregated Results'}</h2>
              <p className="mt-3 max-w-2xl text-base leading-7 text-gray-300">
                {visualReport?.subheadline || 'The backend ran the requested agents, aggregated their outputs, and returned the final student-ready result.'}
              </p>
            </div>
            <button
              onClick={onReset}
              className="inline-flex items-center justify-center rounded-[28px] border border-[#E31937]/40 bg-[#111827] px-6 py-3 text-sm font-semibold text-white transition hover:bg-[#161616]"
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
                  <div key={`${chart.id || 'chart'}-${index}`} className="rounded-[32px] border border-[#E31937]/20 bg-[#111827] p-6 shadow-sm">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-xs uppercase tracking-[0.3em] text-[#FFB81C]">Visual report</p>
                        <h3 className="mt-2 text-xl font-semibold text-white">{chart.title || 'Chart'}</h3>
                      </div>
                      <span className="rounded-full bg-[#0f0f0f] px-3 py-1 text-xs font-semibold text-gray-300">
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
                <div key={`${point}-${index}`} className="rounded-[28px] border border-[#FFB81C]/15 bg-[#111827] p-5 shadow-sm">
                  <p className="text-xs uppercase tracking-[0.3em] text-[#FFB81C]">Story point</p>
                  <p className="mt-3 text-sm leading-7 text-gray-200">{point}</p>
                </div>
              ))
            ) : (
              <div className="rounded-[28px] border border-[#FFB81C]/15 bg-[#111827] p-5 shadow-sm md:col-span-2 xl:col-span-3">
                <p className="text-sm text-gray-300">No highlight text was produced by the aggregator.</p>
              </div>
            )}
          </div>

          <div className="mt-8 rounded-[32px] border border-[#E31937]/20 bg-[#111827] p-5 shadow-sm">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <h3 className="text-xl font-semibold text-white">Workflow trace</h3>
              <p className="text-sm text-gray-300">{visualReport?.section_count || response?.presentation?.sections?.length || 0} report sections prepared</p>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {timeline.slice(0, 6).map((event, index) => (
                <div key={`${event.type || 'event'}-${index}`} className="rounded-2xl border border-white/10 bg-[#0f0f0f] p-4">
                  <p className="text-xs uppercase tracking-[0.25em] text-[#FFB81C]">{formatEventLabel(event.type, event.status)}</p>
                  <p className="mt-2 text-sm font-medium text-white">{event.agent || event.work || event.message || 'Backend update'}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-8 rounded-[32px] border border-[#E31937]/20 bg-[#111827] p-6 shadow-sm">
            <h3 className="text-xl font-semibold text-white">TerpAI dashboard</h3>
            <div className="mt-4 space-y-5">{response ? <Dashboard data={response} /> : <p className="text-sm text-gray-300">Waiting for backend data...</p>}</div>

            {quickActions.length > 0 && (
              <div className="mt-8 rounded-[28px] bg-[#0f0f0f] p-5 shadow-sm">
                <p className="text-sm uppercase tracking-[0.25em] text-[#FFB81C]">Quick actions</p>
                <div className="mt-4 flex flex-wrap gap-3">
                  {quickActions.map((action, index) => (
                    <a
                      key={`${action.label || 'action'}-${index}`}
                      href={action.target || '#'}
                      target={action.target ? '_blank' : undefined}
                      rel={action.target ? 'noreferrer' : undefined}
                      className="rounded-full border border-[#FFB81C]/20 bg-[#FFB81C]/8 px-4 py-2 text-sm font-semibold text-[#FFB81C] shadow-sm transition hover:bg-[#FFB81C]/15"
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
