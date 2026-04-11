'use client'

interface AgentState {
  name: string
  status: string
  description: string
}

interface AgentsPageProps {
  query: string
  agents: AgentState[]
}

const agentColors: Record<string, string> = {
  Initializing: 'bg-[#FEF3C7] text-[#92400E]',
  Running: 'bg-[#DDEBF9] text-[#1D4ED8]',
  Waiting: 'bg-[#E5E7EB] text-[#374151]',
  Completed: 'bg-[#DCFCE7] text-[#166534]',
}

export default function AgentsPage({ query, agents }: AgentsPageProps) {
  return (
    <div className="relative min-h-screen overflow-hidden bg-[#F8FAFC] px-4 py-10 text-[#111827]">
      {/* Background blobs */}
      <div className="absolute top-20 right-10 h-96 w-96 rounded-full bg-[#FFB81C]/5 blur-3xl" />
      <div className="absolute bottom-40 left-20 h-80 w-80 rounded-full bg-[#E31937]/5 blur-3xl" />

      <div className="relative mx-auto w-full max-w-6xl space-y-8">
        <div className="rounded-[36px] border border-[#E31937]/10 bg-white/95 p-8 shadow-[0_30px_90px_-40px_rgba(227,25,55,0.35)] backdrop-blur-xl">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
            <div className="space-y-3">
              <p className="text-sm uppercase tracking-[0.3em] text-[#92400E]">
                Agent launch pad
              </p>
              <h2 className="text-4xl font-black">
                Campus AI agents are running
              </h2>
              <p className="max-w-2xl text-base leading-7 text-[#475569]">
                The Task Agent is orchestrating a team of specialized agents that work in parallel. Each one contributes a different part of the answer.
              </p>
            </div>
            <div className="rounded-3xl bg-[#FFB81C] px-6 py-5 text-white shadow-xl shadow-[#E31937]/20">
              <p className="text-sm uppercase tracking-[0.3em]">Current query</p>
              <p className="mt-4 text-xl font-semibold">{query}</p>
            </div>
          </div>
        </div>

        <div className="space-y-5">
          <div className="grid gap-5 lg:grid-cols-3">
            {[
              { label: 'Lead coordinator', title: 'Task Agent', desc: 'Decides which agents are needed for the campus query and starts them all together.' },
              { label: 'Final fetch', title: 'Aggregation Agent', desc: 'Waits for the parallel agents to finish, then merges their outputs into one clear answer.' },
              { label: 'Campus feel', title: 'UDM Vibe', desc: 'Designed with Maryland red and gold to make the AI workflow feel like a campus experience.' },
            ].map((card, idx) => (
              <div
                key={card.title}
                className="rounded-[32px] border border-[#E31937]/15 bg-white p-6 shadow-sm"
              >
                <p className="text-sm uppercase tracking-[0.3em] text-[#92400E]">
                  {card.label}
                </p>
                <h3 className="mt-3 text-2xl font-bold text-[#111827]">{card.title}</h3>
                <p className="mt-3 text-sm text-[#475569]">{card.desc}</p>
              </div>
            ))}
          </div>

          <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {agents.map((agent, idx) => (
              <div
                key={agent.name}
                className="group overflow-hidden rounded-[32px] border border-[#E31937]/10 bg-white p-6 shadow-sm transition"
              >
                <div className="mb-4 flex items-center justify-between gap-4">
                  <div>
                    <p className="text-lg font-semibold text-[#111827]">{agent.name}</p>
                    <p className="mt-2 text-sm text-[#6B7280]">{agent.description}</p>
                  </div>
                  <span
                    className={`rounded-full px-3 py-1 text-sm font-semibold ${agentColors[agent.status]}`}
                  >
                    {agent.status}
                  </span>
                </div>
                <div className="mt-4 h-3 overflow-hidden rounded-full bg-[#F3F4F6]">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${
                      agent.status === 'Completed'
                        ? 'bg-[#16A34A]'
                        : agent.status === 'Running'
                          ? 'bg-[#2563EB]'
                          : agent.status === 'Initializing'
                            ? 'bg-[#F59E0B]'
                            : 'bg-[#9CA3AF]'
                    }`}
                    style={{
                      width:
                        agent.status === 'Completed' ? '100%' : agent.status === 'Running' ? '65%' : agent.status === 'Initializing' ? '35%' : '10%',
                    }}
                  />
                </div>
                <div className="mt-5 flex items-center gap-2 text-xs uppercase tracking-[0.25em] text-[#9CA3AF]">
                  <span
                    className={`inline-block h-2 w-2 rounded-full ${
                      agent.status === 'Completed'
                        ? 'bg-[#16A34A]'
                        : agent.status === 'Running'
                          ? 'bg-[#2563EB]'
                          : agent.status === 'Initializing'
                            ? 'bg-[#F59E0B]'
                            : 'bg-[#9CA3AF]'
                    }`}
                  />
                  <span>{agent.status}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}