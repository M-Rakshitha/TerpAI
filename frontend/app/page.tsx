// 'use client';

// import { useState } from 'react';
// import PromptPage from '@/components/ai/PromptPage';
// import SimpleResultsPage from '@/components/ai/SimpleResultsPage';

// export default function Home() {
//   const [submittedPrompt, setSubmittedPrompt] = useState<string | null>(null);

//   const handleSubmit = (message: string) => {
//     console.log('Submitted:', message);
//     setSubmittedPrompt(message);
//   };

//   const handleBack = () => {
//     setSubmittedPrompt(null);
//   };

//   if (submittedPrompt) {
//     return <SimpleResultsPage prompt={submittedPrompt} onBack={handleBack} />;
//   }

//   return <PromptPage onSubmit={handleSubmit} />;
// }

'use client';

import { useState } from 'react';
import PromptPage from '@/components/ai/PromptPage';
import AgentsPage from '@/components/ai/AgentsPage';
import ResultsPage from '@/components/ai/ResultsPage';
import { submitQueryWithProgress } from '@/lib/api';
import { QueryResponse, QueryTimelineEvent } from '@/lib/types';

type View = 'prompt' | 'agents' | 'results';

interface LiveStage {
  name: string;
  status: string;
  description: string;
  detail?: string;
  completionMessage?: string;
  steps: { title: string; status: 'running' | 'completed' | 'failed' | 'queued'; message: string }[];
}

export default function Home() {
  const [view, setView] = useState<View>('prompt');
  const [prompt, setPrompt] = useState('');
  const [stages, setStages] = useState<LiveStage[]>([]);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [statusLabel, setStatusLabel] = useState('');

  const handleSubmit = async (message: string) => {
    setPrompt(message);
    setStages([]);
    setResponse(null);
    setStatusLabel('Connecting...');
    setView('agents');

    try {
      const finalResponse = await submitQueryWithProgress(message, handleEvent);
      setResponse(finalResponse);
      setStatusLabel('Aggregation complete. Open the final report.');
    } catch (err) {
      console.error('Backend error:', err);
      setStatusLabel('Failed to reach backend');
    }
  };

  const handleEvent = (event: QueryTimelineEvent) => {
    const type = event.type || '';

    if (type === 'planner_status') {
      const status = event.status || 'running';
      setStatusLabel(status === 'completed' ? 'Planner completed' : 'Planner running...');
      setStages((prev) => upsertStage(prev, {
        name: 'Task Planner',
        status: status === 'completed' ? 'Completed' : 'Running',
        description: 'Analyzing your query and selecting agents',
        detail: event.work || event.message || '',
        steps: [{ title: 'Planning', status: status === 'completed' ? 'completed' : 'running', message: event.work || event.message || 'Planning in progress...' }],
      }));
    }

    if (type === 'agent_status') {
      const agent = event.agent || 'Agent';
      const status = event.status || 'queued';
      const stageStatus =
        status === 'completed' ? 'Completed' :
        status === 'running' ? 'Running' :
        status === 'failed' ? 'Attention' : 'Queued';

      setStatusLabel(`${agent}: ${status}`);
      setStages((prev) => upsertStage(prev, {
        name: agent,
        status: stageStatus,
        description: `Agent handling part of your query`,
        detail: event.work || event.message || '',
        completionMessage: status === 'completed' ? `${agent} finished successfully.` : undefined,
        steps: [{
          title: status,
          status: status === 'completed' ? 'completed' : status === 'running' ? 'running' : status === 'failed' ? 'failed' : 'queued',
          message: event.work || event.message || `${agent} is ${status}`,
        }],
      }));
    }

    if (type === 'aggregator_status') {
      const status = event.status || 'running';
      setStatusLabel(status === 'completed' ? 'Aggregating results...' : 'Finalizing...');
      setStages((prev) => upsertStage(prev, {
        name: 'Aggregator',
        status: status === 'completed' ? 'Completed' : 'Running',
        description: 'Combining all agent outputs into a final answer',
        detail: event.work || event.message || '',
        steps: [{ title: 'Aggregating', status: status === 'completed' ? 'completed' : 'running', message: event.work || event.message || 'Combining results...' }],
      }));
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
    return (
      <ResultsPage
        prompt={prompt}
        response={response}
        onReset={handleReset}
      />
    );
  }

  return <PromptPage onSubmit={handleSubmit} />;
}
