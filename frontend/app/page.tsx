'use client';

import { useMemo, useState } from 'react';
import { QuerySubmitContext } from '@/lib/api';
import PromptPage from '@/components/ai/PromptPage';
import AgentsPage from '@/components/ai/AgentsPage';
import ResultsPage from '@/components/ai/ResultsPage';
import { useQuery } from '@/hooks/useQuery';
import { AgentStepResult, QueryTimelineEvent } from '@/lib/types';

type PageState = 'prompt' | 'agents';

type LiveStage = {
  name: string;
  status: string;
  description: string;
  detail?: string;
  completionMessage?: string;
  steps: { title: string; status: 'running' | 'completed' | 'failed' | 'queued'; message: string }[];
};

export default function Home() {
  const [page, setPage] = useState<PageState>('prompt');
  const [query, setQuery] = useState('');
  const [summaryVisible, setSummaryVisible] = useState(false);
  const { data, loading, error, events, submit, reset } = useQuery();

  const timeline = useMemo<QueryTimelineEvent[]>(() => events, [events]);

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

  const queryNeedsLocation = (message: string) => {
    const lowered = message.toLowerCase();
    return LOCATION_INTENT_TERMS.some((term) => lowered.includes(term));
  };

  const getBrowserLocation = async (
    options?: { enableHighAccuracy?: boolean; timeout?: number; maximumAge?: number },
  ): Promise<{ location: string; coords: { latitude: number; longitude: number } }> => {
    return await new Promise<{ location: string; coords: { latitude: number; longitude: number } }>((resolve, reject) => {
      if (typeof navigator === 'undefined' || !navigator.geolocation) {
        reject(new Error('Geolocation is not available in this browser.'));
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (position) => {
          resolve({
            location: `${position.coords.latitude},${position.coords.longitude}`,
            coords: {
              latitude: position.coords.latitude,
              longitude: position.coords.longitude,
            },
          });
        },
        (error) => reject(error),
        {
          enableHighAccuracy: options?.enableHighAccuracy ?? false,
          timeout: options?.timeout ?? 20000,
          maximumAge: options?.maximumAge ?? 30000,
        },
      );
    });
  };

  const resolveLocationContext = async (message: string): Promise<QuerySubmitContext | null> => {
    if (!queryNeedsLocation(message)) {
      return {};
    }

    try {
      const location = await getBrowserLocation();
      return {
        user_location: location.location,
        current_location_coords: location.coords,
        location_permission_granted: true,
      };
    } catch (error) {
      const geoError = error as GeolocationPositionError | undefined;
      if (geoError?.code === 1) {
        return { location_permission_granted: false };
      }
      // Non-permission geolocation failures (timeout/unavailable) should still
      // submit so backend can request location explicitly without blocking UI flow.
      return {};
    }
  };

  const plannerEvent = useMemo(() => {
    const candidates = timeline.filter((event) => event.type === 'planner_status');
    return candidates[candidates.length - 1] || null;
  }, [timeline]);

  const selectedAgents = useMemo(() => {
    if (plannerEvent?.status === 'completed' && Array.isArray(plannerEvent.tasks) && plannerEvent.tasks.length > 0) {
      return plannerEvent.tasks;
    }
    if (loading) {
      return [];
    }
    return data?.agents_used || [];
  }, [data?.agents_used, loading, plannerEvent]);

  const stages = useMemo<LiveStage[]>(() => {
    const stageMap = new Map<string, LiveStage>();

    const descriptions: Record<string, string> = {
      planner: 'Determines which backend agents should run.',
      schedule: 'Plans deadlines, class timing, and study blocks.',
      dining: 'Finds dining options that fit your budget and preferences.',
      events: 'Surfaces campus events and student activities.',
      finance: 'Analyzes budgets, costs, and spending tradeoffs.',
      navigator: 'Builds directions and campus route guidance.',
      study_resources: 'Locates tutoring, office hours, and academic help.',
      jobs_research: 'Searches internships, research labs, and career leads.',
      aggregator: 'Combines all backend outputs into the final answer.',
    };

    const completionMessages: Record<string, string> = {
      planner: 'Routing complete. Agents selected and launched in parallel.',
      schedule: 'Schedule planning complete with practical execution guidance.',
      dining: 'Dining recommendations complete with ranked options and constraints checks.',
      events: 'Event discovery complete with relevant options and timing details.',
      finance: 'Budget guidance complete with cost-fit and spending recommendations.',
      navigator: 'Navigation complete with route-ready origin and destination details.',
      study_resources: 'Study support complete with tutoring and learning resources.',
      jobs_research: 'Opportunity research complete with actionable next steps.',
      aggregator: 'Aggregation complete. Final cross-agent response is ready.',
    };

    const normalizeStatus = (status?: string) => {
      if (status === 'running' || status === 'retrying') return 'Running';
      if (status === 'completed') return 'Completed';
      if (status === 'failed' || status === 'timeout') return 'Attention';
      if (status === 'no_output') return 'Queued';
      return 'Queued';
    };

    const statusDetail = (status?: string) => {
      if (status === 'running') return 'Task in progress...';
      if (status === 'retrying') return 'Retrying after transient issue...';
      if (status === 'completed') return 'Task done.';
      if (status === 'failed' || status === 'timeout') return 'Task finished with an issue.';
      return 'Queued to run.';
    };

    const coerceStepStatus = (status?: string): 'running' | 'completed' | 'failed' | 'queued' => {
      if (status === 'running') return 'running';
      if (status === 'completed' || status === 'ok') return 'completed';
      if (status === 'failed' || status === 'timeout' || status === 'error') return 'failed';
      return 'queued';
    };

    const extractSubtasks = (agentName: string): string[] => {
      const runningEvents = timeline
        .filter((event) => event.type === 'agent_status' && event.agent === agentName)
        .slice()
        .reverse();
      for (const event of runningEvents) {
        const ctx = event.context_snapshot;
        if (!ctx || typeof ctx !== 'object') continue;
        const subtasks = (ctx as Record<string, unknown>).agent_subtasks;
        if (Array.isArray(subtasks)) {
          const cleaned = subtasks.map((item) => String(item).trim()).filter(Boolean);
          if (cleaned.length > 0) return cleaned;
        }
      }
      return ['Gather required inputs', 'Run agent analysis', 'Finalize structured response'];
    };

    const extractAgentOutput = (agentName: string): Record<string, unknown> | null => {
      const outputs = data?.agent_outputs;
      if (!outputs || typeof outputs !== 'object') return null;
      const output = (outputs as Record<string, unknown>)[agentName];
      if (!output || typeof output !== 'object') return null;
      return output as Record<string, unknown>;
    };

    const buildAgentSteps = (agentName: string, latest: QueryTimelineEvent | undefined) => {
      const subtasks = extractSubtasks(agentName);
      const output = extractAgentOutput(agentName);
      const rawStepResults = Array.isArray(output?.step_results) ? (output?.step_results as AgentStepResult[]) : [];
      const stepEvents = timeline
        .filter((event) => event.type === 'agent_step' && event.agent === agentName)
        .slice();

      if (stepEvents.length > 0 && latest?.status !== 'completed') {
        return subtasks.map((title, index) => {
          const stepIndex = index + 1;
          const latestStepEvent = [...stepEvents].reverse().find((event) => event.step_index === stepIndex);
          if (latestStepEvent) {
            return {
              title,
              status: coerceStepStatus(latestStepEvent.status),
              message: latestStepEvent.message || `Step ${stepIndex} in progress.`,
            };
          }
          const current = latest?.current_step || 1;
          if (stepIndex < current) {
            return { title, status: 'completed' as const, message: `Completed: ${title}` };
          }
          if (stepIndex === current && (latest?.status === 'running' || latest?.status === 'retrying')) {
            return { title, status: 'running' as const, message: `Working on: ${title}` };
          }
          return { title, status: 'queued' as const, message: 'Queued to run.' };
        });
      }

      if (rawStepResults.length > 0) {
        return rawStepResults.map((step, index) => ({
          title: step.subtask || subtasks[index] || `Step ${index + 1}`,
          status: coerceStepStatus(step.status),
          message: step.message || 'Completed.',
        }));
      }

      return subtasks.map((title, index) => {
        const status = latest?.status;
        if (status === 'completed') {
          return {
            title,
            status: 'completed' as const,
            message: `Completed: ${title}`,
          };
        }
        if (status === 'failed' || status === 'timeout') {
          return {
            title,
            status: index === 0 ? ('failed' as const) : ('queued' as const),
            message: index === 0 ? 'Stopped due to an execution issue.' : 'Not started due to earlier failure.',
          };
        }
        if (status === 'running' || status === 'retrying') {
          return {
            title,
            status: index === 0 ? ('running' as const) : ('queued' as const),
            message: index === 0 ? 'In progress...' : 'Waiting for previous step to complete.',
          };
        }
        return {
          title,
          status: 'queued' as const,
          message: 'Queued to run.',
        };
      });
    };

    const liveDetail = (event: QueryTimelineEvent | undefined, fallbackStatus?: string) => {
      if (!event) return statusDetail(fallbackStatus);
      if (event.status === 'running') return event.detail || event.reason || event.work || 'Task in progress...';
      if (event.status === 'retrying') return event.reason || 'Retrying after transient issue...';
      if (event.status === 'completed') return 'Task done.';
      if (event.status === 'failed' || event.status === 'timeout') return event.error || event.detail || 'Task finished with an issue.';
      return statusDetail(event.status || fallbackStatus);
    };

    const plannerEvents = timeline.filter((event) => event.type === 'planner_status');
    const planner = plannerEvents[plannerEvents.length - 1];
    const plannerTasks =
      planner?.tasks && planner.tasks.length > 0
        ? planner.tasks
        : data?.agents_used && data.agents_used.length > 0
          ? data.agents_used
          : [];
    const selectedAgentsLabel = plannerTasks.length > 0 ? `Selected agents: ${plannerTasks.join(', ')}` : 'Selecting backend agents';
    const plannerCompleted = planner?.status === 'completed' || (!!data && plannerTasks.length > 0);
    stageMap.set('planner', {
      name: 'Task Planner',
      status: plannerCompleted ? 'Completed' : normalizeStatus(planner?.status || (loading ? 'running' : 'queued')),
      description: descriptions.planner,
      detail: plannerCompleted ? selectedAgentsLabel : liveDetail(planner || undefined, loading ? 'running' : 'queued'),
      completionMessage: completionMessages.planner,
      steps: [
        {
          title: 'Analyze prompt and detect intent',
          status: plannerCompleted ? 'completed' : loading ? 'running' : 'queued',
          message: plannerCompleted ? selectedAgentsLabel : 'Identifying required agents and constraints.',
        },
      ],
    });

    for (const agent of selectedAgents) {
      const agentEvents = timeline.filter((event) => event.type === 'agent_status' && event.agent === agent);
      const latest = agentEvents[agentEvents.length - 1];
      const fallbackOutput = extractAgentOutput(agent);
      if (agentEvents.length === 0 && !fallbackOutput) {
        continue;
      }

      const displayName = agent.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
      const fallbackCompleted = agentEvents.length === 0 && !!fallbackOutput;
      stageMap.set(agent, {
        name: displayName,
        status: fallbackCompleted ? 'Completed' : normalizeStatus(latest?.status),
        description: descriptions[agent] || 'Backend agent executing the request.',
        detail: fallbackCompleted ? 'Completed from final response payload.' : liveDetail(latest, 'queued'),
        completionMessage:
          (fallbackOutput?.completion_message as string | undefined) ||
          latest?.completion_message ||
          completionMessages[agent] ||
          'Agent workflow complete.',
        steps: buildAgentSteps(agent, latest),
      });
    }

    const aggregatorEvents = timeline.filter((event) => event.type === 'aggregator_status');
    const aggregator = aggregatorEvents[aggregatorEvents.length - 1];
    if (aggregator) {
      stageMap.set('aggregator', {
        name: 'Aggregator',
        status: normalizeStatus(aggregator?.status || (data ? 'completed' : 'queued')),
        description: descriptions.aggregator,
        detail: liveDetail(aggregator || undefined, data ? 'completed' : 'queued'),
        completionMessage: completionMessages.aggregator,
        steps: [
          {
            title: 'Merge agent outputs into final response',
            status: aggregator?.status === 'completed' ? 'completed' : aggregator?.status === 'running' ? 'running' : 'queued',
            message: aggregator?.status === 'completed' ? completionMessages.aggregator : 'Collecting outputs and generating final response.',
          },
        ],
      });
    }

    return Array.from(stageMap.values());
  }, [data, loading, selectedAgents, timeline]);

  const handlePromptSubmit = async (prompt: string) => {
    const trimmed = prompt.trim();
    if (!trimmed) return;

    setQuery(trimmed);
    setSummaryVisible(false);
    setPage('agents');

    try {
      const submitContext = await resolveLocationContext(trimmed);
      if (submitContext === null) {
        setPage('prompt');
        return;
      }
      const firstResponse = await submit(trimmed, submitContext);
      if (firstResponse?.awaiting_user_input && queryNeedsLocation(trimmed)) {
        try {
          const location = await getBrowserLocation({
            enableHighAccuracy: false,
            timeout: 25000,
            maximumAge: 60000,
          });
          await submit(trimmed, {
            user_location: location.location,
            current_location_coords: location.coords,
            location_permission_granted: true,
          });
        } catch {
          // Always send an explicit fallback decision if follow-up location lookup
          // fails, otherwise the backend can remain paused awaiting user input.
          await submit(trimmed, { location_permission_granted: false });
        }
      }
      setSummaryVisible(false);
    } catch {
      // Keep the agents page visible so users see live/error status instead of
      // appearing to remain on the prompt page when the backend is unreachable.
    }
  };

  const handleReset = () => {
    reset();
    setPage('prompt');
    setQuery('');
    setSummaryVisible(false);
  };

  const handleRevealSummary = () => {
    setSummaryVisible(true);
  };

  const statusLabel = loading
    ? 'Live backend updates are streaming in real time.'
    : data?.awaiting_user_input
      ? data?.user_input_request?.prompt || 'Waiting for your current location before running agents.'
    : error
      ? error
      : page === 'agents' && data && !summaryVisible
        ? 'Workflow complete. Reveal the aggregator summary when ready.'
        : 'Waiting for the next backend run.';

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-[#111827]">
      {page === 'prompt' && <PromptPage onSubmit={handlePromptSubmit} />}
      {page === 'agents' && !summaryVisible && (
        <AgentsPage
          query={query}
          stages={stages}
          response={data}
          revealed={summaryVisible}
          onRevealSummary={handleRevealSummary}
          onReset={handleReset}
          statusLabel={statusLabel}
        />
      )}
      {page === 'agents' && summaryVisible && (
        <ResultsPage
          prompt={query}
          response={data}
          revealed={summaryVisible}
          onReveal={handleRevealSummary}
          onReset={handleReset}
        />
      )}
    </div>
  );
}
