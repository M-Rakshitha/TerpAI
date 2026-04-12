'use client';

import { useEffect, useState } from 'react';
import PromptPage from '@/components/ai/PromptPage';
import AgentsPage from '@/components/ai/AgentsPage';
import ResultsPage from '@/components/ai/ResultsPage';
import { QuerySubmitContext, submitQueryWithProgress } from '@/lib/api';
import { QueryResponse, QueryTimelineEvent } from '@/lib/types';

type View = 'prompt' | 'agents' | 'results';

interface LiveStage {
  name: string;
  status: string;
  description: string;
  detail?: string;
  completionMessage?: string;
  progress?: number;
  currentStep?: number;
  totalSteps?: number;
  activity?: string;
  lastUpdatedAt?: string;
  steps: { title: string; status: 'running' | 'completed' | 'failed' | 'queued'; message: string }[];
}

const AGENT_DESCRIPTIONS: Record<string, string> = {
  'Task Planner': 'Analyzing your query and selecting the best agent lineup.',
  dining: 'Finding and ranking dining options from live and fallback data.',
  navigator: 'Preparing route-ready directions and map links for your options.',
  events: 'Collecting relevant campus events and logistics details.',
  finance: 'Summarizing costs and budget fit based on your constraints.',
  schedule: 'Building time-aware study and deadline planning steps.',
  study_resources: 'Compiling tutoring, office hours, and support resources.',
  jobs_research: 'Gathering opportunities and outreach-ready details.',
  aggregator: 'Merging all agent results into a final report.',
};

const LOCATION_INTENT_TERMS = [
  'near me',
  'nearby',
  'around me',
  'current location',
  'walking distance',
  'how do i get',
  'directions',
  'route',
];

function queryNeedsLocation(message: string) {
  const lowered = message.toLowerCase();
  return LOCATION_INTENT_TERMS.some((term) => lowered.includes(term));
}

const LOCATION_CACHE_KEY = 'terpai:last-known-location';

let warmedLocationPromise: Promise<{ location: { lat: number; lng: number } | null; permissionDenied: boolean }> | null = null;

function readCachedLocation(): { lat: number; lng: number } | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    const raw = window.sessionStorage.getItem(LOCATION_CACHE_KEY);
    if (!raw) {
      return null;
    }

    const parsed = JSON.parse(raw) as { lat?: unknown; lng?: unknown };
    const lat = Number(parsed.lat);
    const lng = Number(parsed.lng);
    if (Number.isFinite(lat) && Number.isFinite(lng)) {
      return { lat, lng };
    }
  } catch {
    return null;
  }

  return null;
}

function storeCachedLocation(location: { lat: number; lng: number }) {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    window.sessionStorage.setItem(LOCATION_CACHE_KEY, JSON.stringify(location));
  } catch {
    // Ignore storage failures.
  }
}

function ensureBrowserLocation(options?: { enableHighAccuracy?: boolean; timeout?: number; maximumAge?: number }) {
  if (!warmedLocationPromise) {
    warmedLocationPromise = getBrowserLocation(options).finally(() => {
      warmedLocationPromise = null;
    });
  }

  return warmedLocationPromise;
}

async function getBrowserLocation(
  options?: { enableHighAccuracy?: boolean; timeout?: number; maximumAge?: number },
): Promise<{ location: { lat: number; lng: number } | null; permissionDenied: boolean }> {
  return await new Promise<{ location: { lat: number; lng: number } | null; permissionDenied: boolean }>((resolve) => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      resolve({ location: null, permissionDenied: false });
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const location = {
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        };
        storeCachedLocation(location);
        resolve({ location, permissionDenied: false });
      },
      (error) => {
        resolve({ location: null, permissionDenied: error.code === 1 });
      },
      {
        enableHighAccuracy: options?.enableHighAccuracy ?? false,
        timeout: options?.timeout ?? 30000,
        maximumAge: options?.maximumAge ?? 300000,
      },
    );
  });
}

async function resolveLocationContext(message: string): Promise<QuerySubmitContext> {
  if (!queryNeedsLocation(message)) {
    return {};
  }

  const cached = readCachedLocation();
  if (cached) {
    return {
      location: cached,
      user_location: `${cached.lat},${cached.lng}`,
      current_location_coords: { latitude: cached.lat, longitude: cached.lng },
      location_permission_granted: true,
    };
  }

  const geo = await ensureBrowserLocation({
    enableHighAccuracy: false,
    timeout: 15000,
    maximumAge: 60000,
  });
  if (geo.location) {
    return {
      location: geo.location,
      user_location: `${geo.location.lat},${geo.location.lng}`,
      current_location_coords: { latitude: geo.location.lat, longitude: geo.location.lng },
      location_permission_granted: true,
    };
  }

  return {
    location: null,
    location_permission_granted: geo.permissionDenied ? false : undefined,
  };
}

export default function Home() {
  const [view, setView] = useState<View>('prompt');
  const [prompt, setPrompt] = useState('');
  const [stages, setStages] = useState<LiveStage[]>([]);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [statusLabel, setStatusLabel] = useState('');

  useEffect(() => {
    if (typeof navigator === 'undefined' || !navigator.permissions || !navigator.geolocation) {
      return;
    }

    let cancelled = false;
    navigator.permissions.query({ name: 'geolocation' as PermissionName }).then((permissionStatus) => {
      if (cancelled || permissionStatus.state !== 'granted') {
        return;
      }

      void ensureBrowserLocation({
        enableHighAccuracy: false,
        timeout: 30000,
        maximumAge: 300000,
      });
    }).catch(() => undefined);

    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubmit = async (message: string) => {
    setPrompt(message);
    setStages([]);
    setResponse(null);
    setStatusLabel('Connecting...');
    setView('agents');

    try {
      const submitContext = await resolveLocationContext(message);
      let finalResponse = await submitQueryWithProgress(message, submitContext, handleEvent);

      if (finalResponse?.awaiting_user_input && queryNeedsLocation(message)) {
        const cached = readCachedLocation();
        if (cached) {
          finalResponse = await submitQueryWithProgress(
            message,
            {
              location: cached,
              user_location: `${cached.lat},${cached.lng}`,
              current_location_coords: { latitude: cached.lat, longitude: cached.lng },
              location_permission_granted: true,
            },
            handleEvent,
          );
          setResponse(finalResponse);
          setStatusLabel('Aggregation complete. Open the final report.');
          return;
        }

        const geo = await ensureBrowserLocation({
          enableHighAccuracy: false,
          timeout: 30000,
          maximumAge: 300000,
        });

        finalResponse = await submitQueryWithProgress(
          message,
          geo.location
            ? {
                location: geo.location,
                user_location: `${geo.location.lat},${geo.location.lng}`,
                current_location_coords: { latitude: geo.location.lat, longitude: geo.location.lng },
                location_permission_granted: true,
              }
            : {
                location: null,
                location_permission_granted: geo.permissionDenied ? false : undefined,
              },
          handleEvent,
        );
      }

      setResponse(finalResponse);
      if (finalResponse?.awaiting_user_input) {
        setStatusLabel(finalResponse.user_input_request?.prompt || 'Waiting for location access.');
        return;
      }

      setStatusLabel('Aggregation complete. Open the final report.');
    } catch (err) {
      console.error('Backend error:', err);
      setStatusLabel('Failed to reach backend');
    }
  };

  const handleEvent = (event: QueryTimelineEvent) => {
    const type = event.type || '';
    const timestamp = event.timestamp || new Date().toISOString();

    const inferProgress = (status: string, currentStep?: number, totalSteps?: number) => {
      if (status === 'completed') return 100;
      if (typeof currentStep === 'number' && typeof totalSteps === 'number' && totalSteps > 0) {
        return Math.max(5, Math.min(98, Math.round((currentStep / totalSteps) * 100)));
      }
      if (status === 'running') return 18;
      if (status === 'failed') return 100;
      return 8;
    };

    const toStageStatus = (status: string): string => {
      if (status === 'completed') return 'Completed';
      if (status === 'running' || status === 'retrying') return 'Running';
      if (status === 'failed' || status === 'timeout') return 'Attention';
      return 'Queued';
    };

    const eventText =
      event.subtask ||
      event.message ||
      event.detail ||
      event.reason ||
      event.work ||
      'Processing update...';

    if (type === 'planner_status') {
      const status = event.status || 'running';
      setStatusLabel(status === 'completed' ? 'Planner completed' : eventText);
      setStages((prev) =>
        upsertStage(prev, {
          name: 'Task Planner',
          status: toStageStatus(status),
          description: AGENT_DESCRIPTIONS['Task Planner'],
          detail: eventText,
          activity: eventText,
          currentStep: event.current_step,
          totalSteps: event.total_steps,
          progress: inferProgress(status, event.current_step, event.total_steps),
          lastUpdatedAt: timestamp,
          steps: [
            {
              title: event.subtask || 'Planning pipeline',
              status: status === 'completed' ? 'completed' : 'running',
              message: eventText,
            },
          ],
        }),
      );
    }

    if (type === 'agent_status') {
      const agent = (event.agent || 'Agent').toLowerCase();
      const status = event.status || 'queued';
      const stageStatus = toStageStatus(status);

      setStatusLabel(`${agent}: ${eventText}`);
      setStages((prev) =>
        upsertStage(prev, {
          name: agent,
          status: stageStatus,
          description: AGENT_DESCRIPTIONS[agent] || 'Agent handling part of your query.',
          detail: eventText,
          activity: eventText,
          currentStep: event.current_step,
          totalSteps: event.total_steps,
          progress: inferProgress(status, event.current_step, event.total_steps),
          lastUpdatedAt: timestamp,
          completionMessage: status === 'completed' ? `${agent} finished successfully.` : undefined,
          steps: [
            {
              title: event.subtask || event.work || 'Active task',
              status: status === 'completed' ? 'completed' : status === 'running' ? 'running' : status === 'failed' ? 'failed' : 'queued',
              message: eventText,
            },
          ],
        }),
      );
    }

    if (type === 'agent_step') {
      const agent = (event.agent || 'Agent').toLowerCase();
      const status = event.status || 'running';
      const stageStatus = toStageStatus(status);
      const stepTitle = event.subtask || 'Working on task';

      setStatusLabel(`${agent}: ${eventText}`);
      setStages((prev) => {
        const existing = prev.find((s) => s.name === agent);
        const nextSteps = existing?.steps ? [...existing.steps] : [];
        const mappedStatus: 'running' | 'completed' | 'failed' | 'queued' =
          status === 'completed' ? 'completed' : status === 'failed' || status === 'timeout' ? 'failed' : 'running';
        nextSteps.push({
          title: stepTitle,
          status: mappedStatus,
          message: eventText,
        });

        return upsertStage(prev, {
          name: agent,
          status: stageStatus,
          description: AGENT_DESCRIPTIONS[agent] || 'Agent handling part of your query.',
          detail: eventText,
          activity: stepTitle,
          currentStep: event.step_index || event.current_step,
          totalSteps: event.total_steps,
          progress: inferProgress(status, event.step_index || event.current_step, event.total_steps),
          lastUpdatedAt: timestamp,
          completionMessage: status === 'completed' ? event.message : existing?.completionMessage,
          steps: nextSteps.slice(-10),
        });
      });
    }

    if (type === 'aggregator_status') {
      const status = event.status || 'running';
      setStatusLabel(status === 'completed' ? 'Aggregation complete' : eventText);
      setStages((prev) =>
        upsertStage(prev, {
          name: 'Aggregator',
          status: toStageStatus(status),
          description: AGENT_DESCRIPTIONS.aggregator,
          detail: eventText,
          activity: eventText,
          currentStep: event.current_step,
          totalSteps: event.total_steps,
          progress: inferProgress(status, event.current_step, event.total_steps),
          lastUpdatedAt: timestamp,
          steps: [
            {
              title: event.subtask || 'Combining outputs',
              status: status === 'completed' ? 'completed' : 'running',
              message: eventText,
            },
          ],
        }),
      );
    }

    if (type === 'query_result' && event.payload && typeof event.payload === 'object') {
      setResponse(event.payload as QueryResponse);
      setStatusLabel('Complete');
    }

    if ((type === 'final_response' || type === 'complete') && event.payload && typeof event.payload === 'object') {
      setResponse(event.payload as QueryResponse);
      setStatusLabel('Complete');
    }
  };

  const upsertStage = (prev: LiveStage[], updated: LiveStage): LiveStage[] => {
    const index = prev.findIndex((s) => s.name === updated.name);
    if (index === -1) return [...prev, updated];
    const next = [...prev];
    next[index] = { ...next[index], ...updated };
    return next;
  };

  const handleReset = () => {
    setPrompt('');
    setStages([]);
    setResponse(null);
    setStatusLabel('');
    setView('prompt');
  };

  const handleReveal = () => {
    setView('results');
  };

  if (view === 'agents') {
    return (
      <AgentsPage
        query={prompt}
        stages={stages}
        response={response}
        onRevealSummary={handleReveal}
        onReset={handleReset}
        statusLabel={statusLabel}
      />
    );
  }

  if (view === 'results') {
    return <ResultsPage prompt={prompt} response={response} onReset={handleReset} />;
  }

  return <PromptPage onSubmit={handleSubmit} />;
}
