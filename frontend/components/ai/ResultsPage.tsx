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

const chartColors = ['#E31937', '#FFB81C', '#1D4ED8', '#16A34A', '#0F172A']

const NOISE_TERMS = [
  'failed',
  'fallback',
  'declined',
  'error',
  'timeout',
  'pipeline',
  'agent',
  'trace',
]

function isRelevantText(value: string) {
  const lowered = value.toLowerCase()
  return !NOISE_TERMS.some((term) => lowered.includes(term))
}

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
        originMarker.bindPopup('Start location')
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
      if (mapInstance) {
        mapInstance.remove()
      }
    }
  }, [center.lat, center.lng, destinations, origin])

  return <div ref={mapRef} className="h-[360px] w-full" />
}

export default function ResultsPage({ prompt, response, onReset }: ResultsPageProps) {
  const summary = response?.presentation?.summary
  const visualReport = response?.presentation?.visual_report
  const diningOptions = response?.results?.dining?.options || []

  const highlights = (summary?.highlights || []).filter((item) => typeof item === 'string' && isRelevantText(item))

  const topDining = diningOptions
    .filter((item) => Number(item.distance_min) > 0)
    .slice()
    .sort((a, b) => a.distance_min - b.distance_min)
    .slice(0, 8)

  const sections = response?.presentation?.sections || []
  const navigationItems = (sections.find((section) => section?.id === 'navigation')?.items || []) as Record<string, unknown>[]
  const primaryRoute = navigationItems.length > 0 ? navigationItems[0] : null
  const routesByOption = ((primaryRoute?.routes_by_option as Record<string, unknown>[]) || []).slice(0, 6)

  const destinationCoords = topDining
    .map((item) => ({ name: item.name, coord: parseCoordinates(item.coordinates) }))
    .filter((item): item is { name: string; coord: LatLng } => Boolean(item.coord))

  const originCoord = parseCoordText(response?.results?.navigator?.origin)
  const mapCenter = originCoord || destinationCoords[0]?.coord || { lat: 38.9869, lng: -76.9426 }

  const computedMetrics = useMemo<QueryVisualMetric[]>(() => {
    const openCount = topDining.filter((item) => item.hours_open).length
    const avgWalk = topDining.length > 0 ? Math.round(topDining.reduce((acc, item) => acc + item.distance_min, 0) / topDining.length) : 0
    const routeCount = routesByOption.length

    return [
      { label: 'Top matches', value: topDining.length, suffix: 'places', tone: 'accent' },
      { label: 'Open now', value: openCount, suffix: 'places', tone: 'success' },
      { label: 'Avg walk', value: avgWalk, suffix: 'min', tone: 'warning' },
      { label: 'Route options', value: routeCount, suffix: 'routes', tone: 'neutral' },
    ]
  }, [routesByOption.length, topDining])

  const diningDistanceChart: QueryVisualChart = {
    id: 'distance_ranked',
    title: 'Closest Options (Walking Minutes)',
    kind: 'bar',
    data: topDining.map((item) => ({ label: item.name, value: item.distance_min })),
    colors: ['#FFB81C', '#E31937', '#1D4ED8'],
  }

  const routePieChart: QueryVisualChart = {
    id: 'route_distribution',
    title: 'Open vs Not Open',
    kind: 'pie',
    data: [
      { label: 'Open now', value: topDining.filter((item) => item.hours_open).length, color: '#16A34A' },
      { label: 'Unknown/closed', value: Math.max(0, topDining.length - topDining.filter((item) => item.hours_open).length), color: '#64748B' },
    ],
  }

  const usefulCharts = [
    ...(visualReport?.charts || []).filter((chart) => Array.isArray(chart.data) && chart.data.length > 0),
    ...(topDining.length > 0 ? [diningDistanceChart, routePieChart] : []),
  ]

  const routeRows: RouteItem[] =
    routesByOption.length > 0
      ? routesByOption.map((route) => ({
          destination: String(route.destination || 'Route'),
          description: typeof route.description === 'string' ? route.description : undefined,
          walk_minutes: typeof route.walk_minutes === 'number' ? route.walk_minutes : null,
          map_url: typeof route.map_url === 'string' ? route.map_url : undefined,
        }))
      : topDining.slice(0, 5).map((item) => ({ destination: item.name, walk_minutes: item.distance_min }))

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
              <p className="text-sm uppercase tracking-[0.28em] text-[#FFB81C]">Final Report</p>
              <h2 className="mt-2 text-4xl font-black text-white">{visualReport?.headline || summary?.title || 'Best options for your prompt'}</h2>
              <p className="mt-3 max-w-2xl text-base leading-7 text-gray-300">
                {visualReport?.subheadline || `Prompt: ${prompt}`}
              </p>
            </div>
            <button
              onClick={onReset}
              className="inline-flex items-center justify-center rounded-[28px] border border-[#E31937]/40 bg-[#111827] px-6 py-3 text-sm font-semibold text-white transition hover:bg-[#161616]"
            >
              Ask another question
            </button>
          </div>

          <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {(visualReport?.metrics && visualReport.metrics.length > 0 ? visualReport.metrics : computedMetrics).map((metric, index) => (
              <div key={`${metric.label || 'metric'}-${index}`} className={`rounded-[28px] border p-5 shadow-sm ${metricToneStyles[metric.tone || 'neutral'] || metricToneStyles.neutral}`}>
                <p className="text-xs uppercase tracking-[0.3em] opacity-80">{metric.label || 'Metric'}</p>
                <p className="mt-4 text-3xl font-black">{formatMetricValue(metric)}</p>
              </div>
            ))}
          </div>

          <div className="mt-8 grid gap-6 xl:grid-cols-2">
            {usefulCharts.slice(0, 4).map((chart, index) => (
              <div key={`${chart.id || 'chart'}-${index}`} className="rounded-[32px] border border-[#E31937]/20 bg-[#111827] p-6 shadow-sm">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs uppercase tracking-[0.3em] text-[#FFB81C]">Data insight</p>
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

          {(destinationCoords.length > 0 || routeRows.length > 0) && (
            <div className="mt-8 rounded-[32px] border border-[#E31937]/20 bg-[#111827] p-6 shadow-sm">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.3em] text-[#FFB81C]">Route map</p>
                  <h3 className="mt-2 text-xl font-semibold text-white">Interactive map of top destinations</h3>
                </div>
                {typeof primaryRoute?.map_url === 'string' && (
                  <a
                    href={primaryRoute.map_url}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded-full border border-[#FFB81C]/25 bg-[#FFB81C]/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[#FFB81C]"
                  >
                    Open native route
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

          {highlights.length > 0 && (
            <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {highlights.slice(0, 6).map((point, index) => (
                <div key={`${point}-${index}`} className="rounded-[28px] border border-[#FFB81C]/15 bg-[#111827] p-5 shadow-sm">
                  <p className="text-xs uppercase tracking-[0.3em] text-[#FFB81C]">Key takeaway</p>
                  <p className="mt-3 text-sm leading-7 text-gray-200">{point}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
