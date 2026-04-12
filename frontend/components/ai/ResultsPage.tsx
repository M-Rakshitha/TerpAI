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

function clampPercent(value: number) {
  return Math.max(8, Math.min(100, value))
}

function meterWidth(current: number, maximum: number) {
  if (maximum <= 0) return '8%'
  return `${clampPercent((current / maximum) * 100)}%`
}

function isVisibleMetricValue(value: QueryVisualMetric['value']) {
  if (typeof value === 'number') return value !== 0
  if (typeof value === 'string') return value.trim() !== '' && value.trim() !== '0'
  return Boolean(value)
}

function ExternalLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 rounded-full border border-[#FFD200]/35 bg-[#FFD200]/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-[#FFD200] transition hover:bg-[#FFD200]/15"
    >
      {label}
      <span aria-hidden="true">↗</span>
    </a>
  )
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

function GoogleRouteMap({
  center,
  origin,
  destinations,
}: {
  center: LatLng
  origin: LatLng | null
  destinations: Array<{ name: string; coord: LatLng }>
}) {
  const mapRef = useRef<HTMLDivElement | null>(null)
  const mapInstance = useRef<any>(null)

  useEffect(() => {
    let isMounted = true
    const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY

    if (!apiKey) {
      console.warn('Google Maps API key not configured')
      return
    }

    const initializeMap = async () => {
      if (typeof window === 'undefined' || !mapRef.current) return

      // Load Google Maps script
      if (!(window as any).google?.maps) {
        const script = document.createElement('script')
        script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=routes`
        script.async = true
        script.defer = true
        script.onload = () => {
          if (isMounted) setupMap()
        }
        script.onerror = () => console.error('Failed to load Google Maps API')
        document.head.appendChild(script)
      } else {
        setupMap()
      }
    }

    const setupMap = () => {
      if (!isMounted || !mapRef.current) return
      const google = (window as any).google

      // Create map
      mapInstance.current = new google.maps.Map(mapRef.current, {
        zoom: 14,
        center: { lat: center.lat, lng: center.lng },
        styles: [
          { elementType: 'geometry', stylers: [{ color: '#242f3e' }] },
          { elementType: 'labels.text.stroke', stylers: [{ color: '#242f3e' }] },
          { elementType: 'labels.text.fill', stylers: [{ color: '#746855' }] },
          {
            featureType: 'administrative.locality',
            elementType: 'labels.text.fill',
            stylers: [{ color: '#d59563' }],
          },
          {
            featureType: 'poi',
            elementType: 'labels.text.fill',
            stylers: [{ color: '#d59563' }],
          },
          {
            featureType: 'poi.park',
            elementType: 'geometry',
            stylers: [{ color: '#263c3f' }],
          },
          {
            featureType: 'road',
            elementType: 'geometry',
            stylers: [{ color: '#38414e' }],
          },
          {
            featureType: 'road',
            elementType: 'geometry.stroke',
            stylers: [{ color: '#212a37' }],
          },
          {
            featureType: 'road.highway',
            elementType: 'geometry',
            stylers: [{ color: '#746855' }],
          },
          {
            featureType: 'road.highway',
            elementType: 'geometry.stroke',
            stylers: [{ color: '#1f2835' }],
          },
          {
            featureType: 'road.highway.controlled_access',
            elementType: 'geometry',
            stylers: [{ color: '#4e7c59' }],
          },
          {
            featureType: 'road.highway.controlled_access',
            elementType: 'geometry.stroke',
            stylers: [{ color: '#27230d' }],
          },
          {
            featureType: 'road.local',
            elementType: 'labels.text.fill',
            stylers: [{ color: '#9ca5a8' }],
          },
          {
            featureType: 'transit',
            elementType: 'geometry',
            stylers: [{ color: '#2f3948' }],
          },
          {
            featureType: 'transit.station',
            elementType: 'labels.text.fill',
            stylers: [{ color: '#d59563' }],
          },
          {
            featureType: 'water',
            elementType: 'geometry',
            stylers: [{ color: '#17263c' }],
          },
          {
            featureType: 'water',
            elementType: 'labels.text.fill',
            stylers: [{ color: '#515c6d' }],
          },
          {
            featureType: 'water',
            elementType: 'labels.text.stroke',
            stylers: [{ color: '#17263c' }],
          },
        ],
      })

      // Add origin marker (red)
      if (origin) {
        new google.maps.Marker({
          position: { lat: origin.lat, lng: origin.lng },
          map: mapInstance.current,
          title: 'Start',
          icon: {
            path: google.maps.SymbolPath.CIRCLE,
            scale: 10,
            fillColor: '#E31937',
            fillOpacity: 1,
            strokeColor: 'white',
            strokeWeight: 2,
          },
        })
      }

      // Add destination markers (gold) and draw routes
      destinations.forEach((dest, idx) => {
        new google.maps.Marker({
          position: { lat: dest.coord.lat, lng: dest.coord.lng },
          map: mapInstance.current,
          title: dest.name,
          icon: {
            path: google.maps.SymbolPath.CIRCLE,
            scale: 8,
            fillColor: '#FFB81C',
            fillOpacity: 0.95,
            strokeColor: 'white',
            strokeWeight: 2,
          },
          label: {
            text: String(idx + 1),
            color: '#000',
            fontSize: '11px',
            fontWeight: 'bold',
          },
        })

        // Draw polyline between origin and destination
        if (origin) {
          new google.maps.Polyline({
            path: [
              { lat: origin.lat, lng: origin.lng },
              { lat: dest.coord.lat, lng: dest.coord.lng },
            ],
            geodesic: true,
            strokeColor: '#60A5FA',
            strokeOpacity: 0.75,
            strokeWeight: 3,
            map: mapInstance.current,
          })
        }
      })

      // Fit bounds to show all markers
      const bounds = new google.maps.LatLngBounds()
      if (origin) {
        bounds.extend({ lat: origin.lat, lng: origin.lng })
      }
      destinations.forEach((dest) => {
        bounds.extend({ lat: dest.coord.lat, lng: dest.coord.lng })
      })
      if (origin || destinations.length > 0) {
        mapInstance.current.fitBounds(bounds, { top: 24, right: 24, bottom: 24, left: 24 })
      }
    }

    initializeMap()

    return () => {
      isMounted = false
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
    .filter((item) => item && item.name)
    .slice()
    .sort((a, b) => {
      const aDist = Number(a.distance_min) || 999
      const bDist = Number(b.distance_min) || 999
      return aDist - bDist
    })
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
    navigator.origin &&
    navigator.destination
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

  const maxDiningDistance = topDining.reduce((max, item) => {
    const dist = Number(item.distance_min) || 0
    return Math.max(max, dist)
  }, 0)
  const weeklyBudgetTotal = finance ? finance.weekly_spent + finance.budget_remaining : 0
  const weeklySpentPercent = finance && weeklyBudgetTotal > 0 ? Math.round((finance.weekly_spent / weeklyBudgetTotal) * 100) : 0
  const weeklyRemainingPercent = finance && weeklyBudgetTotal > 0 ? 100 - weeklySpentPercent : 0

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
    const avgWalk = topDining.length > 0 
      ? Math.round(topDining.reduce((acc, item) => acc + (Number(item.distance_min) || 0), 0) / topDining.length)
      : 0
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
        data: topDining.map((item) => ({ label: item.name, value: Number(item.distance_min) || 0 })).filter(d => d.value > 0),
        colors: ['#FFB81C', '#E31937', '#1D4ED8'],
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
        ].filter((datum) => Number(datum.value || 0) > 0),
      }
    : null

  const usefulCharts = [diningDistanceChart, financeChart]
    .filter((chart): chart is QueryVisualChart => Boolean(chart))
    .filter((chart) => Array.isArray(chart.data) && chart.data.length > 0)
    .slice(0, 4)

  const visibleMetrics = computedMetrics.filter((metric) => isVisibleMetricValue(metric.value))

  const renderTag = (label: string, tone: 'gold' | 'red' | 'blue' | 'green' | 'neutral' = 'neutral') => {
    const styles: Record<typeof tone, string> = {
      gold: 'bg-[#FFD200]/15 text-[#FDE68A] border-[#FFD200]/30',
      red: 'bg-[#E31937]/15 text-[#FCA5A5] border-[#E31937]/30',
      blue: 'bg-[#1D4ED8]/15 text-[#BFDBFE] border-[#1D4ED8]/30',
      green: 'bg-[#16A34A]/15 text-[#BBF7D0] border-[#16A34A]/30',
      neutral: 'bg-white/5 text-gray-200 border-white/10',
    }

    return (
      <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${styles[tone]}`}>
        {label}
      </span>
    )
  }

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

          {visibleMetrics.length > 0 && (
            <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {visibleMetrics.map((metric, index) => (
              <div key={`${metric.label || 'metric'}-${index}`} className={`rounded-[28px] border p-5 shadow-sm ${metricToneStyles[metric.tone || 'neutral'] || metricToneStyles.neutral}`}>
                <p className="text-xs uppercase tracking-[0.3em] opacity-80">{metric.label || 'Metric'}</p>
                <p className="mt-4 text-3xl font-black">{formatMetricValue(metric)}</p>
              </div>
              ))}
            </div>
          )}

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
                  <GoogleRouteMap center={mapCenter} origin={originCoord} destinations={destinationCoords} />
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

            <div className="mt-8 space-y-6">
            {topDining.length > 0 && (
              <div className="rounded-[30px] border border-[#FFB81C]/20 bg-[#111827] p-6">
                <p className="text-xs uppercase tracking-[0.25em] text-[#FFB81C]">Dining picks</p>
                <h3 className="mt-2 text-xl font-semibold text-white">Best nearby options</h3>
                <div className="mt-4 space-y-3">
                  {topDining.slice(0, 5).map((item, index) => (
                    <div key={item.name} className="rounded-2xl border border-white/10 bg-[#0f0f0f] p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-white">{item.name}</p>
                          <p className="mt-1 text-xs text-gray-400">{Number(item.distance_min) > 0 ? `${item.distance_min} min walk` : 'Distance unknown'}</p>
                        </div>
                        {renderTag(item.hours_open ? 'Open now' : 'Hours unknown', item.hours_open ? 'green' : 'neutral')}
                      </div>
                      <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/5">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-[#FFD200] via-[#E31937] to-[#60A5FA]"
                          style={{ width: meterWidth(Math.max(maxDiningDistance - (Number(item.distance_min) || maxDiningDistance), 0), Math.max(maxDiningDistance, 1)) }}
                        />
                      </div>
                      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                        {renderTag(item.budget_ok ? 'Fits budget' : 'Budget stretch', item.budget_ok ? 'blue' : 'red')}
                        {item.dietary_tags.slice(0, 3).map((tag) => renderTag(tag, 'gold'))}
                        {item.source_url && <ExternalLink href={item.source_url} label="Source" />}
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
                    <div key={`${event.title}-${idx}`} className="rounded-2xl border border-white/10 bg-[#0f0f0f] p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-white">{event.title}</p>
                          <p className="mt-1 text-xs text-gray-400">{event.location}</p>
                        </div>
                        {event.free_food ? renderTag('Free food', 'green') : renderTag('Campus event', 'gold')}
                      </div>
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        {renderTag(formatDateTime(event.start) || event.start, 'neutral')}
                        {event.tags.slice(0, 3).map((tag) => renderTag(tag, 'blue'))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {finance && (
              <div className="rounded-[30px] border border-[#FFB81C]/20 bg-[#111827] p-6">
                <p className="text-xs uppercase tracking-[0.25em] text-[#FFB81C]">Finance</p>
                <h3 className="mt-2 text-xl font-semibold text-white">Budget snapshot</h3>
                <div className="mt-4 rounded-2xl border border-white/10 bg-[#0f0f0f] p-4">
                  <div className="flex items-center justify-between text-xs uppercase tracking-[0.2em] text-gray-400">
                    <span>Spent</span>
                    <span>Remaining</span>
                  </div>
                  <div className="mt-3 h-3 overflow-hidden rounded-full bg-white/5">
                    <div className="h-full rounded-full bg-gradient-to-r from-[#E31937] to-[#FFB81C]" style={{ width: `${weeklySpentPercent}%` }} />
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-3">
                    <div className="rounded-xl border border-white/10 bg-[#111827] p-3">
                      <p className="text-xs text-gray-400">Weekly spent</p>
                      <p className="mt-1 text-lg font-bold text-white">${finance.weekly_spent.toFixed(2)}</p>
                    </div>
                    <div className="rounded-xl border border-white/10 bg-[#111827] p-3">
                      <p className="text-xs text-gray-400">Remaining</p>
                      <p className="mt-1 text-lg font-bold text-white">${finance.budget_remaining.toFixed(2)}</p>
                    </div>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2 text-xs">
                    {renderTag(`${weeklySpentPercent}% spent`, 'red')}
                    {renderTag(`${weeklyRemainingPercent}% remaining`, 'green')}
                  </div>
                </div>
                <p className="mt-4 text-sm leading-7 text-gray-300">{finance.suggestion}</p>
              </div>
            )}

            {schedule && (
              <div className="rounded-[30px] border border-[#FFB81C]/20 bg-[#111827] p-6">
                <p className="text-xs uppercase tracking-[0.25em] text-[#FFB81C]">Study Plan</p>
                <h3 className="mt-2 text-xl font-semibold text-white">Time blocks and next deadline</h3>
                {schedule.next_deadline?.title && (
                  <div className="mt-4 rounded-2xl border border-white/10 bg-[#0f0f0f] p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-[#FFD200]">Next deadline</p>
                    <p className="mt-2 text-sm font-semibold text-white">{schedule.next_deadline.title}</p>
                    <p className="mt-1 text-xs text-gray-400">{formatDateTime(schedule.next_deadline.due) || schedule.next_deadline.due}</p>
                  </div>
                )}
                <div className="mt-4 space-y-3">
                  {(schedule.study_blocks || []).slice(0, 5).map((block, idx) => (
                    <div key={`${block.subject}-${idx}`} className="rounded-2xl border border-white/10 bg-[#0f0f0f] p-4 text-sm text-gray-200">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-semibold text-white">{block.subject}</p>
                          <p className="mt-1 text-xs text-gray-400">{block.start} - {block.end}</p>
                        </div>
                        {renderTag(block.type, 'gold')}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(tutoring.length > 0 || officeHours.length > 0) && (
              <div className="rounded-[30px] border border-[#FFB81C]/20 bg-[#111827] p-6">
                <p className="text-xs uppercase tracking-[0.25em] text-[#FFB81C]">Study Resources</p>
                <h3 className="mt-2 text-xl font-semibold text-white">Help options for your courses</h3>
                <div className="mt-4 space-y-4">
                  {tutoring.length > 0 && (
                    <div>
                      <div className="mb-2 flex items-center justify-between">
                        <p className="text-sm font-semibold text-white">Tutoring</p>
                        {renderTag(`${tutoring.length} listings`, 'blue')}
                      </div>
                      <div className="space-y-2">
                        {tutoring.map((item, idx) => (
                          <div key={`${item.service}-${idx}`} className="rounded-2xl border border-white/10 bg-[#0f0f0f] p-4 text-sm">
                            <p className="font-semibold text-white">{item.service} · {item.subject}</p>
                            <p className="mt-1 text-xs text-gray-400">{item.schedule}</p>
                            <p className="mt-1 text-xs text-gray-400">{item.location}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {officeHours.length > 0 && (
                    <div>
                      <div className="mb-2 flex items-center justify-between">
                        <p className="text-sm font-semibold text-white">Office hours</p>
                        {renderTag(`${officeHours.length} listings`, 'gold')}
                      </div>
                      <div className="space-y-2">
                        {officeHours.map((item, idx) => (
                          <div key={`${item.professor}-${idx}`} className="rounded-2xl border border-white/10 bg-[#0f0f0f] p-4 text-sm">
                            <p className="font-semibold text-white">{item.professor} ({item.course})</p>
                            <p className="mt-1 text-xs text-gray-400">{item.time}</p>
                            <p className="mt-1 text-xs text-gray-400">{item.room}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {(topJobs.length > 0 || topLabs.length > 0) && (
              <div className="rounded-[30px] border border-[#FFB81C]/20 bg-[#111827] p-6">
                <p className="text-xs uppercase tracking-[0.25em] text-[#FFB81C]">Opportunities</p>
                <h3 className="mt-2 text-xl font-semibold text-white">Jobs and research leads</h3>
                <div className="mt-4 space-y-4">
                  {topJobs.length > 0 && (
                    <div>
                      <div className="mb-2 flex items-center justify-between">
                        <p className="text-sm font-semibold text-white">Jobs</p>
                        {renderTag(`${topJobs.length} roles`, 'red')}
                      </div>
                      <div className="grid gap-3">
                        {topJobs.map((job, idx) => (
                          <div key={`${job.title}-${idx}`} className="rounded-2xl border border-white/10 bg-[#0f0f0f] p-4">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <p className="text-sm font-semibold text-white">{job.title}</p>
                                <p className="mt-1 text-xs text-gray-400">{job.department}</p>
                              </div>
                              {renderTag(job.pay, 'gold')}
                            </div>
                            <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/5">
                              <div className="h-full rounded-full bg-gradient-to-r from-[#E31937] to-[#FFD200]" style={{ width: `${Math.max(36, 100 - idx * 12)}%` }} />
                            </div>
                            <div className="mt-3 flex flex-wrap gap-2">
                              <ExternalLink href={job.apply_url} label="Apply" />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {topLabs.length > 0 && (
                    <div>
                      <div className="mb-2 flex items-center justify-between">
                        <p className="text-sm font-semibold text-white">Research labs</p>
                        {renderTag(`${topLabs.length} labs`, 'blue')}
                      </div>
                      <div className="grid gap-3">
                        {topLabs.map((lab, idx) => (
                          <div key={`${lab.pi}-${idx}`} className="rounded-2xl border border-white/10 bg-[#0f0f0f] p-4">
                            <p className="text-sm font-semibold text-white">Lab: {lab.pi}</p>
                            <p className="mt-1 text-xs text-gray-400">{lab.department}</p>
                            <p className="mt-1 text-xs text-gray-400">{lab.topic}</p>
                            <p className="mt-2 text-xs text-[#FFD200]">{lab.contact}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {jobsResearch?.cold_email && (
                    <div className="rounded-2xl border border-[#FFD200]/20 bg-[#0f0f0f] p-4">
                      <p className="text-xs uppercase tracking-[0.25em] text-[#FFD200]">Cold email draft</p>
                      <p className="mt-2 text-sm leading-7 text-gray-200">{jobsResearch.cold_email}</p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
