from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Location(BaseModel):
    lat: float
    lng: float


class QueryRequest(BaseModel):
    message: str = Field(min_length=1)
    debug_trace_context: bool = False
    location: Location | None = None
    user_location: str | None = None
    current_location_coords: dict[str, float] | None = None
    location_permission_granted: bool | None = None


class StudyBlock(BaseModel):
    start: str
    end: str
    subject: str
    type: Literal["review", "practice", "reading"]


class NextDeadline(BaseModel):
    title: str
    due: str


class ScheduleResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    agent: Literal["schedule"]
    study_blocks: list[StudyBlock]
    next_deadline: NextDeadline


class DiningOption(BaseModel):
    name: str
    distance_min: int
    budget_ok: bool
    hours_open: bool
    dietary_tags: list[str]


class DiningResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    agent: Literal["dining"]
    options: list[DiningOption]


class EventItem(BaseModel):
    title: str
    location: str
    start: str
    free_food: bool
    tags: list[str]


class EventsResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    agent: Literal["events"]
    events: list[EventItem]


class FinanceResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    agent: Literal["finance"]
    weekly_spent: float
    budget_remaining: float
    suggestion: str


class NavigatorResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    agent: Literal["navigator"]
    origin: str
    destination: str
    walk_minutes: int
    steps: list[str]
    map_url: str


class TutoringItem(BaseModel):
    service: str
    subject: str
    schedule: str
    location: str


class OfficeHourItem(BaseModel):
    professor: str
    course: str
    time: str
    room: str


class StudyResourcesResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    agent: Literal["study_resources"]
    tutoring: list[TutoringItem]
    office_hours: list[OfficeHourItem]


class JobItem(BaseModel):
    title: str
    department: str
    pay: str
    apply_url: str


class LabItem(BaseModel):
    pi: str
    department: str
    topic: str
    contact: str


class JobsResearchResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    agent: Literal["jobs_research"]
    jobs: list[JobItem]
    labs: list[LabItem]
    cold_email: str


class QueryResults(BaseModel):
    schedule: ScheduleResult | None = None
    dining: DiningResult | None = None
    events: EventsResult | None = None
    finance: FinanceResult | None = None
    navigator: NavigatorResult | None = None
    study_resources: StudyResourcesResult | None = None
    jobs_research: JobsResearchResult | None = None


class QueryResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    query: str
    agents_used: list[str]
    results: QueryResults
    presentation: dict[str, Any] | None = None
    agent_execution: dict[str, Any] | None = None
    agent_outputs: dict[str, Any] | None = None


class TaskPlannerContext(BaseModel):
    budget: float | None
    deadline_mentioned: bool
    location_mentioned: str | None
    enriched_query: str | None = None  # Descriptive rewrite of user message
    ai_enrichment_used: bool | None = None
    ai_routing_used: bool | None = None
    ai_error: str | None = None


class TaskPlannerResponse(BaseModel):
    tasks: list[Literal[
        "schedule",
        "dining",
        "events",
        "finance",
        "navigator",
        "study_resources",
        "jobs_research",
    ]]
    priority: Literal["high", "medium", "low"]
    context: TaskPlannerContext


class AgentExecutionResult(BaseModel):
    agents_used: list[str]
    results: dict[str, Any]


class GoogleCalendarTokenPayload(BaseModel):
    refresh_token: str = Field(min_length=8)


class GoogleCalendarLinkTokenPayload(BaseModel):
    """Server-to-server link from the Next.js OAuth callback (protected by shared secret)."""

    user_sub: str = Field(min_length=1)
    refresh_token: str = Field(min_length=8)


class GoogleCalendarEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    location: str | None = None
    start: str = Field(description="ISO 8601 datetime or date")
    end: str | None = Field(default=None, description="ISO 8601 datetime; defaults to start + 1h")
    description: str | None = None


class GoogleCalendarEventLinkCreate(GoogleCalendarEventCreate):
    """Create event on behalf of user_sub (Next.js server only, shared secret)."""

    user_sub: str = Field(min_length=1)


class GoogleCalendarStatusResponse(BaseModel):
    connected: bool


class GoogleCalendarEventResponse(BaseModel):
    ok: bool
    event_id: str | None = None
    html_link: str | None = None
    detail: str | None = None
