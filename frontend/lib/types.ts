export interface QueryResponse {
  query: string;
  agents_used: string[];
  results: {
    schedule: ScheduleResult | null;
    dining: DiningResult | null;
    events: EventsResult | null;
    finance: FinanceResult | null;
    navigator: NavigatorResult | null;
    study_resources: StudyResourcesResult | null;
    jobs_research: JobsResearchResult | null;
  };
}

export interface ScheduleResult {
  agent: "schedule";
  study_blocks: { start: string; end: string; subject: string; type: string }[];
  next_deadline: { title: string; due: string };
}

export interface DiningResult {
  agent: "dining";
  options: { name: string; distance_min: number; budget_ok: boolean; hours_open: boolean; dietary_tags: string[] }[];
}

export interface EventsResult {
  agent: "events";
  events: { title: string; location: string; start: string; free_food: boolean; tags: string[] }[];
}

export interface FinanceResult {
  agent: "finance";
  weekly_spent: number;
  budget_remaining: number;
  suggestion: string;
}

export interface NavigatorResult {
  agent: "navigator";
  origin: string;
  destination: string;
  walk_minutes: number;
  steps: string[];
  map_url: string;
}

export interface StudyResourcesResult {
  agent: "study_resources";
  tutoring: { service: string; subject: string; schedule: string; location: string }[];
  office_hours: { professor: string; course: string; time: string; room: string }[];
}

export interface JobsResearchResult {
  agent: "jobs_research";
  jobs: { title: string; department: string; pay: string; apply_url: string }[];
  labs: { pi: string; department: string; topic: string; contact: string }[];
  cold_email: string;
}