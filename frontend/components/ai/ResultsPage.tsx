'use client'

import { useEffect, useMemo, useRef } from 'react'
import { QueryResponse, QueryVisualChart, QueryVisualMetric } from '@/lib/types'
import {
  Bar,
  BarChart,
  Cell,
  CartesianGrid,
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

type LatLng = { lat: number; lng: number }

type RouteItem = {
  destination: string
  description?: string
  walk_minutes?: number | null
  map_url?: string
}

const metricToneStyles: Record<string, string> = {
  accent: 'bg-[#FFFBEB] text-[#92400E] border-[#FCD34D]',
  success: 'bg-[#ECFDF5] text-[#166534] border-[#86EFAC]',
  warning: 'bg-[#FFF7ED] text-[#9A3412] border-[#FDBA74]',
  neutral: 'bg-[#F8FAFC] text-[#334155] border-[#E2E8F0]',
}

const chartColors = ['#C8102E', '#FFD200', '#1D4ED8', '#16A34A', '#0F172A']

function parseCoordText(value: unknown): LatLng | null {
  if (typeof value !== 'string') return null
  const parts = value.split(',').map((part) => Number(part.trim()))
  if (parts.length !== 2 || Number.isNaN(parts[0]) || Number.isNaN(parts[1])) return null
  return { lat: parts[0], lng: parts[1] }
}

function parseCoordinates(value: unknown): LatLng | null {
  if (Array.isArray(value) && value.length >= 2) {
    const lat = Number(value[0])
    const lng = Number(value[1])
    if (!Number.isNaN(lat) && !Number.isNaN(lng)) return { lat, lng }
  }
  if (value && typeof value === 'object') {
    const candidate = value as Record<string, unknown>
    const lat = Number(candidate.latitude ?? candidate.lat)
    const lng = Number(candidate.longitude ?? candidate.lng)
    if (!Number.isNaN(lat) && !Number.isNaN(lng)) return { lat, lng }
  }
  return null
}

function formatMetricValue(metric: QueryVisualMetric) {
  const rawValue = metric.value ?? 0
  const suffix = metric.suffix ? ` ${metric.suffix}` : ''
  return `${rawValue}${suffix}`
}

function formatDateTime(value?: string) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date)
}

function renderChart(chart: QueryVisualChart) {
  const chartData = Array.isArray(chart.data) ? chart.data : []
  const palette = chart.colors && chart.colors.length > 0 ? chart.colors : chartColors

  if (chart.kind === 'pie') {
    return (
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie data={chartData} dataKey="value" nameKey="label" cx="50%" cy="50%" outerRadius={78} innerRadius={44} paddingAngle={4}>
            {chartData.map((entry, index) => (
              <Cell key={`${chart.id || 'pie'}-${entry.label || index}`} fill={entry.color || palette[index % palette.length]} />
            ))}
          </Pie>
          <Tooltip />
        </PieChart>
      </ResponsiveContainer>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#223041" />
        <XAxis dataKey="label" tickLine={false} axisLine={false} fontSize={11} stroke="#94A3B8" />
        <YAxis tickLine={false} axisLine={false} fontSize={11} stroke="#94A3B8" />
        <Tooltip />
        <Bar dataKey="value" radius={[10, 10, 0, 0]}>
          {chartData.map((entry, index) => (
            <Cell key={`${chart.id || 'bar'}-${entry.label || index}`} fill={entry.color || palette[index % palette.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

function LeafletRouteMap({
  center,
  origin,
  destinations,
}: {
  center: LatLng
  origin: LatLng | null
  destinations: Array<{ name: string; coord: LatLng }>
}) {
  const mapRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    let isMounted = true
    let mapInstance: any = null

    const ensureLeaflet = async () => {
      if (typeof window === 'undefined') return
      const doc = window.document

      if (!doc.getElementById('leaflet-css')) {
        const link = doc.createElement('link')
        link.id = 'leaflet-css'
        link.rel = 'stylesheet'
        link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'
        doc.head.appendChild(link)
      }

      const loadScript = () =>
        new Promise<void>((resolve, reject) => {
          if ((window as Window & { L?: any }).L) {
            resolve()
            return
          }
          const existing = doc.getElementById('leaflet-js') as HTMLScriptElement | null
          if (existing) {
            existing.addEventListener('load', () => resolve(), { once: true })
            existing.addEventListener('error', () => reject(new Error('Failed to load Leaflet script')), { once: true })
            return
          }
          const script = doc.createElement('script')
          script.id = 'leaflet-js'
          script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
          script.async = true
          script.onload = () => resolve()
          script.onerror = () => reject(new Error('Failed to load Leaflet script'))
          doc.body.appendChild(script)
        })

      await loadScript()
      if (!isMounted || !mapRef.current) return

      const L = (window as Window & { L?: any }).L
      if (!L) return

      mapInstance = L.map(mapRef.current, { zoomControl: true }).setView([center.lat, center.lng], 14)
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
      }).addTo(mapInstance)

      if (origin) {
        const originMarker = L.circleMarker([origin.lat, origin.lng], {
          radius: 7,
          color: '#E31937',
          fillColor: '#E31937',
          fillOpacity: 1,
        }).addTo(mapInstance)
        originMarker.bindPopup('Start')
      }

      destinations.forEach((dest) => {
        const marker = L.circleMarker([dest.coord.lat, dest.coord.lng], {
          radius: 6,
          color: '#FFB81C',
          fillColor: '#FFB81C',
          fillOpacity: 0.95,
        }).addTo(mapInstance)
        marker.bindPopup(dest.name)

        if (origin) {
          L.polyline(
            [
              [origin.lat, origin.lng],
              [dest.coord.lat, dest.coord.lng],
            ],
            {
              color: '#60A5FA',
              weight: 3,
              opacity: 0.75,
              dashArray: '5, 7',
            },
          ).addTo(mapInstance)
        }
      })

      const boundsPoints = [
        ...(origin ? [[origin.lat, origin.lng]] : []),
        ...destinations.map((dest) => [dest.coord.lat, dest.coord.lng]),
      ]
      if (boundsPoints.length > 1) {
        mapInstance.fitBounds(boundsPoints, { padding: [24, 24] })
      }
    }

    ensureLeaflet().catch(() => undefined)

    return () => {
      isMounted = false
      if (mapInstance) mapInstance.remove()
    }
  }, [center.lat, center.lng, destinations, origin])

  return <div ref={mapRef} className="h-[360px] w-full" />
}

export default function ResultsPage({ prompt, response, onReset }: ResultsPageProps) {

  const schedule = response?.results?.schedule
  const dining = response?.results?.dining
  const events = response?.results?.events
  const finance = response?.results?.finance
  const navigator = response?.results?.navigator
  const studyResources = response?.results?.study_resources
  const jobsResearch = response?.results?.jobs_research

  const diningOptions = dining?.options || []
  const topDining = diningOptions
    .filter((item) => Number(item.distance_min) > 0)
    .slice()
    .sort((a, b) => a.distance_min - b.distance_min)
    .slice(0, 8)

  const topEvents = (events?.events || []).slice(0, 6)
  const topJobs = (jobsResearch?.jobs || []).slice(0, 5)
  const topLabs = (jobsResearch?.labs || []).slice(0, 4)
  const tutoring = (studyResources?.tutoring || []).slice(0, 5)
  const officeHours = (studyResources?.office_hours || []).slice(0, 5)

  const destinationText = navigator?.destination || ''
  const destinationCoord = destinationText ? parseCoordText(destinationText) : null
  const destinationCoords = destinationCoord ? [{ name: destinationText, coord: destinationCoord }] : []
  const originCoord = parseCoordText(navigator?.origin)
  const mapCenter = originCoord || destinationCoords[0]?.coord || { lat: 38.9869, lng: -76.9426 }

  const hasNavigationMap = Boolean(
    navigator &&
    navigator.map_url &&
    navigator.origin &&
    navigator.destination &&
    originCoord &&
    destinationCoord,
  )

  const routeRows: RouteItem[] = navigator
    ? [
        {
          destination: navigator.destination,
          walk_minutes: navigator.walk_minutes,
          description: navigator.steps?.slice(0, 2).join(' '),
          map_url: navigator.map_url,
        },
      ]
    : []

  const answerHeadline = useMemo(() => {
    if (navigator?.destination) return `Best route to ${navigator.destination}`
    if (topDining.length > 0) return `Top dining options near you`
    if (topEvents.length > 0) return `Upcoming events that match your request`
    if (schedule?.next_deadline?.title) return `Plan around your next deadline`
    if (topJobs.length > 0 || topLabs.length > 0) return `Career and research opportunities found`
    if (finance) return `Budget snapshot ready`
    return 'Your answer is ready'
  }, [finance, navigator?.destination, schedule?.next_deadline?.title, topDining.length, topEvents.length, topJobs.length, topLabs.length])

  const answerSubline = useMemo(() => {
    if (navigator?.steps?.length) return navigator.steps[0]
    if (dining?.ai_recommendation) return dining.ai_recommendation
    if (finance?.suggestion) return finance.suggestion
    if (topEvents.length > 0) return `${topEvents.length} event options prepared with time and location details.`
    return `Prompt: ${prompt}`
  }, [dining?.ai_recommendation, finance?.suggestion, navigator?.steps, prompt, topEvents.length])

  const computedMetrics = useMemo<QueryVisualMetric[]>(() => {
    const openCount = topDining.filter((item) => item.hours_open).length
    const avgWalk = topDining.length > 0 ? Math.round(topDining.reduce((acc, item) => acc + item.distance_min, 0) / topDining.length) : 0
    const studyBlocks = schedule?.study_blocks?.length || 0

    return [
      { label: 'Matches found', value: topDining.length + topEvents.length + topJobs.length + topLabs.length, suffix: 'items', tone: 'accent' },
      { label: 'Open now', value: openCount, suffix: 'places', tone: 'success' },
      { label: 'Average walk', value: avgWalk, suffix: 'min', tone: 'warning' },
      { label: 'Planned blocks', value: studyBlocks, suffix: 'sessions', tone: 'neutral' },
    ]
  }, [schedule?.study_blocks?.length, topDining, topEvents.length, topJobs.length, topLabs.length])

  const diningDistanceChart: QueryVisualChart | null = topDining.length > 0
    ? {
        id: 'distance_ranked',
        title: 'Dining Distance (Walking Minutes)',
        kind: 'bar',
        data: topDining.map((item) => ({ label: item.name, value: item.distance_min })),
        colors: ['#FFB81C', '#E31937', '#1D4ED8'],
      }
    : null

  const eventsChart: QueryVisualChart | null = topEvents.length > 0
    ? {
        id: 'events_index',
        title: 'Events Snapshot',
        kind: 'bar',
        data: topEvents.map((item, idx) => ({ label: `Event ${idx + 1}`, value: item.free_food ? 2 : 1 })),
        colors: ['#1D4ED8', '#16A34A'],
      }
    : null

  const financeChart: QueryVisualChart | null = finance
    ? {
        id: 'budget_health',
        title: 'Budget Health',
        kind: 'pie',
        data: [
          { label: 'Spent', value: Math.max(0, finance.weekly_spent), color: '#E31937' },
          { label: 'Remaining', value: Math.max(0, finance.budget_remaining), color: '#16A34A' },
        ],
      }
    : null

  const usefulCharts = [diningDistanceChart, eventsChart, financeChart]
    .filter((chart): chart is QueryVisualChart => Boolean(chart))
    .filter((chart) => Array.isArray(chart.data) && chart.data.length > 0)
    .slice(0, 4)

  return (
    <div className="relative min-h-screen overflow-hidden px-4 py-10 text-white">
      <div className="fixed inset-0 bg-gradient-to-br from-[#001f3f] via-[#0a0a0a] to-[#000000]" />
      <div
        className="fixed inset-0 opacity-10"
        style={{
          backgroundImage:
            'radial-gradient(ellipse at 20% 20%, rgba(227, 25, 55, 0.08) 0%, transparent 50%), radial-gradient(ellipse at 80% 80%, rgba(255, 184, 28, 0.06) 0%, transparent 50%)',
        }}
      />

      <div className="relative mx-auto w-full max-w-6xl space-y-8">
        <div className="rounded-[36px] border border-[#E31937]/20 bg-[#1a1a1a]/90 p-8 shadow-2xl shadow-red-500/10 backdrop-blur-2xl">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm uppercase tracking-[0.28em] text-[#FFB81C]">Your Answer</p>
              <h2 className="mt-2 text-4xl font-black text-white">{answerHeadline}</h2>
              <p className="mt-3 max-w-3xl text-base leading-7 text-gray-300">{answerSubline}</p>
            </div>
            <button
              onClick={onReset}
              className="inline-flex items-center justify-center rounded-[28px] border border-[#F59E0B]/40 bg-[#111827] px-6 py-3 text-sm font-semibold text-[#FDE68A] shadow-lg shadow-black/30 transition hover:border-[#FBBF24] hover:bg-[#1f2937] hover:text-[#FEF3C7]"
            >
              Ask another question
            </button>
          </div>

          <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {computedMetrics.map((metric, index) => (
              <div key={`${metric.label || 'metric'}-${index}`} className={`rounded-[28px] border p-5 shadow-sm ${metricToneStyles[metric.tone || 'neutral'] || metricToneStyles.neutral}`}>
                <p className="text-xs uppercase tracking-[0.3em] opacity-80">{metric.label || 'Metric'}</p>
                <p className="mt-4 text-3xl font-black">{formatMetricValue(metric)}</p>
              </div>
            ))}
          </div>

          {usefulCharts.length > 0 && (
            <div className="mt-8 grid gap-6 xl:grid-cols-2">
              {usefulCharts.map((chart, index) => (
                <div key={`${chart.id || 'chart'}-${index}`} className="rounded-[32px] border border-[#E31937]/20 bg-[#111827] p-6 shadow-sm">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-xs uppercase tracking-[0.3em] text-[#FFB81C]">Insight</p>
                      <h3 className="mt-2 text-xl font-semibold text-white">{chart.title || 'Chart'}</h3>
                    </div>
                    <span className="rounded-full bg-[#0f0f0f] px-3 py-1 text-xs font-semibold text-gray-300">
                      {chart.kind || 'bar'}
                    </span>
                  </div>
                  <div className="mt-5">{renderChart(chart)}</div>
                </div>
              ))}
            </div>
          )}

          {hasNavigationMap && (
            <div className="mt-8 rounded-[32px] border border-[#C8102E]/30 bg-[#111827] p-6 shadow-sm">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.3em] text-[#FFD200]">Navigation Route</p>
                  <h3 className="mt-2 text-xl font-semibold text-white">Exact route from {navigator?.origin} to {navigator?.destination}</h3>
                </div>
                {typeof navigator?.map_url === 'string' && (
                  <a
                    href={navigator.map_url}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded-full border border-[#FFD200]/35 bg-[#FFD200]/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[#FFD200]"
                  >
                    Open map
                  </a>
                )}
              </div>

              <div className="mt-5 grid gap-5 xl:grid-cols-[1.1fr_1fr]">
                <div className="overflow-hidden rounded-2xl border border-white/10 bg-[#0f0f0f]">
                  <LeafletRouteMap center={mapCenter} origin={originCoord} destinations={destinationCoords} />
                </div>

                <div className="space-y-3">
                  {routeRows.slice(0, 6).map((route, index) => (
                    <div key={`route-${index}`} className="rounded-2xl border border-white/10 bg-[#0f0f0f] p-4">
                      <p className="text-xs uppercase tracking-[0.25em] text-[#FFB81C]">Destination</p>
                      <p className="mt-2 text-sm font-semibold text-white">{route.destination}</p>
                      {route.walk_minutes !== null && route.walk_minutes !== undefined && (
                        <p className="mt-1 text-xs text-gray-300">Approx walk: {route.walk_minutes} min</p>
                      )}
                      {route.description && <p className="mt-2 text-xs leading-6 text-gray-300">{route.description}</p>}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          <div className="mt-8 grid gap-6 xl:grid-cols-2">
            {topDining.length > 0 && (
              <div className="rounded-[30px] border border-[#FFB81C]/20 bg-[#111827] p-6">
                <p className="text-xs uppercase tracking-[0.25em] text-[#FFB81C]">Dining picks</p>
                <h3 className="mt-2 text-xl font-semibold text-white">Best nearby options</h3>
                <div className="mt-4 space-y-3">
                  {topDining.slice(0, 5).map((item) => (
                    <div key={item.name} className="rounded-xl border border-white/10 bg-[#0f0f0f] p-3">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-semibold text-white">{item.name}</p>
                        <p className="text-xs text-gray-300">{item.distance_min} min walk</p>
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                        <span className={`rounded-full px-2 py-1 ${item.hours_open ? 'bg-emerald-500/20 text-emerald-300' : 'bg-zinc-500/20 text-zinc-300'}`}>
                          {item.hours_open ? 'Open now' : 'Hours unknown'}
                        </span>
                        {typeof item.budget_ok === 'boolean' && (
                          <span className={`rounded-full px-2 py-1 ${item.budget_ok ? 'bg-blue-500/20 text-blue-300' : 'bg-rose-500/20 text-rose-300'}`}>
                            {item.budget_ok ? 'Fits budget' : 'May exceed budget'}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {topEvents.length > 0 && (
              <div className="rounded-[30px] border border-[#FFB81C]/20 bg-[#111827] p-6">
                <p className="text-xs uppercase tracking-[0.25em] text-[#FFB81C]">Events</p>
                <h3 className="mt-2 text-xl font-semibold text-white">Upcoming matches</h3>
                <div className="mt-4 space-y-3">
                  {topEvents.map((event, idx) => (
                    <div key={`${event.title}-${idx}`} className="rounded-xl border border-white/10 bg-[#0f0f0f] p-3">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-semibold text-white">{event.title}</p>
                        {event.free_food && <span className="rounded-full bg-emerald-500/20 px-2 py-1 text-xs text-emerald-300">Free food</span>}
                      </div>
                      <p className="mt-1 text-xs text-gray-300">{event.location}</p>
                      <p className="mt-1 text-xs text-gray-400">{formatDateTime(event.start) || event.start}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {finance && (
              <div className="rounded-[30px] border border-[#FFB81C]/20 bg-[#111827] p-6">
                <p className="text-xs uppercase tracking-[0.25em] text-[#FFB81C]">Finance</p>
                <h3 className="mt-2 text-xl font-semibold text-white">Budget snapshot</h3>
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-xl border border-white/10 bg-[#0f0f0f] p-3">
                    <p className="text-xs text-gray-400">Weekly spent</p>
                    <p className="mt-1 text-lg font-bold text-white">${finance.weekly_spent.toFixed(2)}</p>
                  </div>
                  <div className="rounded-xl border border-white/10 bg-[#0f0f0f] p-3">
                    <p className="text-xs text-gray-400">Remaining</p>
                    <p className="mt-1 text-lg font-bold text-white">${finance.budget_remaining.toFixed(2)}</p>
                  </div>
                </div>
                <p className="mt-4 text-sm text-gray-300">{finance.suggestion}</p>
              </div>
            )}

            {schedule && (
              <div className="rounded-[30px] border border-[#FFB81C]/20 bg-[#111827] p-6">
                <p className="text-xs uppercase tracking-[0.25em] text-[#FFB81C]">Study Plan</p>
                <h3 className="mt-2 text-xl font-semibold text-white">Time blocks and next deadline</h3>
                {schedule.next_deadline?.title && (
                  <div className="mt-4 rounded-xl border border-white/10 bg-[#0f0f0f] p-3">
                    <p className="text-sm font-semibold text-white">{schedule.next_deadline.title}</p>
                    <p className="mt-1 text-xs text-gray-400">{formatDateTime(schedule.next_deadline.due) || schedule.next_deadline.due}</p>
                  </div>
                )}
                <div className="mt-3 space-y-2">
                  {(schedule.study_blocks || []).slice(0, 5).map((block, idx) => (
                    <div key={`${block.subject}-${idx}`} className="rounded-xl border border-white/10 bg-[#0f0f0f] p-3 text-sm text-gray-200">
                      <p className="font-semibold text-white">{block.subject}</p>
                      <p className="text-xs text-gray-400">{block.start} - {block.end} · {block.type}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(tutoring.length > 0 || officeHours.length > 0) && (
              <div className="rounded-[30px] border border-[#FFB81C]/20 bg-[#111827] p-6">
                <p className="text-xs uppercase tracking-[0.25em] text-[#FFB81C]">Study Resources</p>
                <h3 className="mt-2 text-xl font-semibold text-white">Help options for your courses</h3>
                <div className="mt-4 space-y-2">
                  {tutoring.map((item, idx) => (
                    <div key={`${item.service}-${idx}`} className="rounded-xl border border-white/10 bg-[#0f0f0f] p-3 text-sm">
                      <p className="font-semibold text-white">{item.service} · {item.subject}</p>
                      <p className="mt-1 text-xs text-gray-400">{item.schedule} · {item.location}</p>
                    </div>
                  ))}
                  {officeHours.map((item, idx) => (
                    <div key={`${item.professor}-${idx}`} className="rounded-xl border border-white/10 bg-[#0f0f0f] p-3 text-sm">
                      <p className="font-semibold text-white">{item.professor} ({item.course})</p>
                      <p className="mt-1 text-xs text-gray-400">{item.time} · {item.room}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(topJobs.length > 0 || topLabs.length > 0) && (
              <div className="rounded-[30px] border border-[#FFB81C]/20 bg-[#111827] p-6">
                <p className="text-xs uppercase tracking-[0.25em] text-[#FFB81C]">Opportunities</p>
                <h3 className="mt-2 text-xl font-semibold text-white">Jobs and research leads</h3>
                <div className="mt-4 space-y-3">
                  {topJobs.map((job, idx) => (
                    <div key={`${job.title}-${idx}`} className="rounded-xl border border-white/10 bg-[#0f0f0f] p-3">
                      <p className="text-sm font-semibold text-white">{job.title}</p>
                      <p className="mt-1 text-xs text-gray-400">{job.department} · {job.pay}</p>
                    </div>
                  ))}
                  {topLabs.map((lab, idx) => (
                    <div key={`${lab.pi}-${idx}`} className="rounded-xl border border-white/10 bg-[#0f0f0f] p-3">
                      <p className="text-sm font-semibold text-white">Lab: {lab.pi}</p>
                      <p className="mt-1 text-xs text-gray-400">{lab.department} · {lab.topic}</p>
                    </div>
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
