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
  presentation?: QueryPresentation | null;
  agent_execution?: QueryExecution | null;
  agent_outputs?: Record<string, unknown> | null;
  user_input_request?: {
    needs_user_input?: boolean;
    required_fields?: string[];
    permission?: string;
    prompt?: string;
    fallback_location?: string;
    continuing_with_fallback?: boolean;
  } | null;
  awaiting_user_input?: boolean;
  pipeline_paused?: boolean;
  location_fallback_used?: boolean;
  location_default?: string;
}

export interface QueryPresentation {
  layout?: string;
  summary?: QuerySummary;
  sections?: QuerySection[];
  quick_actions?: QueryQuickAction[];
  visual_report?: QueryVisualReport | null;
}

export interface QuerySummary {
  title?: string;
  query?: string;
  active_agents?: string[];
  highlights?: string[];
}

export interface QuerySection {
  id?: string;
  title?: string;
  agent?: string;
  style?: string;
  items?: unknown[];
  meta?: Record<string, unknown>;
}

export interface QueryQuickAction {
  label?: string;
  agent?: string;
  action?: string;
  target?: string;
}

export interface QueryVisualReport {
  headline?: string;
  subheadline?: string;
  metrics?: QueryVisualMetric[];
  charts?: QueryVisualChart[];
  story_points?: string[];
  section_count?: number;
}

export interface QueryVisualMetric {
  label?: string;
  value?: number | string;
  suffix?: string;
  tone?: 'accent' | 'success' | 'warning' | 'neutral' | string;
}

export interface QueryVisualChart {
  id?: string;
  title?: string;
  kind?: 'bar' | 'pie' | 'line' | string;
  data?: QueryVisualChartDatum[];
  colors?: string[];
}

export interface QueryVisualChartDatum {
  label?: string;
  value?: number;
  detail?: string;
  color?: string;
}

export interface QueryExecution {
  active_agents?: string[];
  timeline?: QueryTimelineEvent[];
}

export interface QueryTimelineEvent {
  type?: string;
  agent?: string;
  status?: string;
  timestamp?: string;
  request_id?: string;
  message?: string;
  detail?: string;
  reason?: string;
  error?: string;
  elapsed_ms?: number;
  tasks?: string[];
  work?: string;
  ai_output_preview?: string;
  payload?: unknown;
  context_snapshot?: Record<string, unknown>;
  current_step?: number;
  total_steps?: number;
  completion_message?: string;
  step_index?: number;
  subtask?: string;
  pipeline_paused?: boolean;
  required_fields?: string[];
  fallback_location?: string;
  continuing_with_fallback?: boolean;
}

export interface AgentStepResult {
  step?: string;
  subtask?: string;
  status?: string;
  message?: string;
  evidence_keys?: string[];
}

export interface ScheduleResult {
  agent: "schedule";
  study_blocks: { start: string; end: string; subject: string; type: string }[];
  next_deadline: { title: string; due: string };
}

export interface DiningResult {
  agent: "dining";
  route_preview?: {
    origin?: string;
    destination?: string;
  };
  options: {
    name: string;
    distance_min: number;
    budget_ok: boolean;
    hours_open: boolean;
    dietary_tags: string[];
    source_url?: string | null;
    coordinates?: [number, number] | null;
    vegan_evidence?: boolean;
  }[];
  menu_recommendations?: {
    name?: string;
    menu_highlights?: string[];
    estimated_meal_price?: number | null;
    source?: string;
    source_url?: string | null;
    menu_items_under_budget?: { item?: string; price?: number }[];
    detail_text?: string;
    data_points?: Record<string, string | number | boolean | null>;
  }[];
  warning?: string;
  follow_up_questions?: string[];
  ai_recommendation?: string;
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
  options?: string[];
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