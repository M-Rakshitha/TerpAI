'use client';

import { useEffect, useState } from 'react';
import PromptPage from '@/components/ai/PromptPage';
import AgentsPage from '@/components/ai/AgentsPage';
import ResultsPage from '@/components/ai/ResultsPage';

type PageState = 'prompt' | 'agents' | 'results';

type AgentState = {
  name: string;
  status: string;
  description: string;
};

export default function Home() {
  const [page, setPage] = useState<PageState>('prompt');
  const [query, setQuery] = useState('');
  const [result, setResult] = useState('');
  const [agents, setAgents] = useState<AgentState[]>([]);

  useEffect(() => {
    const timers: Array<ReturnType<typeof setTimeout>> = [];

    if (page === 'agents') {
      timers.push(
        setTimeout(() => {
          setAgents((current) =>
            current.map((agent) => {
              if (agent.name === 'Task Agent') {
                return { ...agent, status: 'Completed' };
              }
              if (agent.name === 'Aggregation Agent') {
                return { ...agent, status: 'Running' };
              }
              return agent;
            })
          );
        }, 1200)
      );

      timers.push(
        setTimeout(() => {
          setAgents((current) =>
            current.map((agent) => {
              if (['Search Agent', 'Location Agent', 'Insight Agent'].includes(agent.name)) {
                return { ...agent, status: 'Completed' };
              }
              if (agent.name === 'Aggregation Agent') {
                return { ...agent, status: 'Completed' };
              }
              return agent;
            })
          );
          setResult(
            `Nearest Chick-fil-A is 0.5 miles away at 123 Main St, just off the University District. The Aggregation Agent combines location, search, and insight data into one final recommendation.`
          );
          setPage('results');
        }, 3200)
      );
    }

    return () => timers.forEach((timer) => clearTimeout(timer));
  }, [page]);

  const handlePromptSubmit = (prompt: string) => {
    const trimmed = prompt.trim();
    if (!trimmed) return;

    setQuery(trimmed);
    setResult('');
    setAgents([
      {
        name: 'Task Agent',
        status: 'Initializing',
        description: 'Analyzes the query and assigns the right AI workers.',
      },
      {
        name: 'Search Agent',
        status: 'Running',
        description: 'Searches for relevant locations and matches.',
      },
      {
        name: 'Location Agent',
        status: 'Running',
        description: 'Identifies the closest location and travel details.',
      },
      {
        name: 'Insight Agent',
        status: 'Running',
        description: 'Generates contextual recommendations from the search results.',
      },
      {
        name: 'Aggregation Agent',
        status: 'Waiting',
        description: 'Collects the agent outputs and generates the final visualization.',
      },
    ]);
    setPage('agents');
  };

  const handleReset = () => {
    setPage('prompt');
    setQuery('');
    setResult('');
    setAgents([]);
  };

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-[#111827]">
      {page === 'prompt' && <PromptPage onSubmit={handlePromptSubmit} />}
      {page === 'agents' && <AgentsPage query={query} agents={agents} />}
      {page === 'results' && <ResultsPage prompt={query} result={result} onReset={handleReset} />}
    </div>
  );
}
