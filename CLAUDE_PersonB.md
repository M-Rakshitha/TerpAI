# CLAUDE.md — TerpAI · Person B (Frontend + UX)

## Project overview

TerpAI is a multi-agent AI platform for University of Maryland students. It unifies Testudo, ELMS, Handshake, dining, events, and research into a single conversational assistant. The user types a natural language query, and the backend returns a structured JSON response containing outputs from multiple specialized agents. You are responsible for rendering that response as a beautiful, interactive dashboard.

You are responsible for everything the user sees: the Next.js app, Auth0 login UI, chat interface, all card components, maps, charts, and animations.

---

## Tech stack

- **Framework**: Next.js 14 (App Router)
- **Styling**: TailwindCSS
- **Components**: ShadCN UI
- **Animations**: Framer Motion
- **Charts**: Recharts or Plotly
- **Maps**: Google Maps JS API (`@react-google-maps/api`)
- **Auth**: Auth0 (`@auth0/nextjs-auth0`)
- **HTTP client**: `axios` or native `fetch`
- **Package manager**: npm

## Current implementation notes

- The frontend should treat the websocket stream as the primary source of truth for progress updates and use the HTTP response as the final result payload.
- Live agent progress should show only the current running or queued step, not every historical step at once.
- Clear stale query results when a new request is submitted so the previous run does not mask live updates.
- The dashboard should still render gracefully if some agent results are `null`, but it should prefer the live response over any local fallback state.
- Keep the existing query bar and card layout responsive, but do not reintroduce mock data as the default path when the real backend is available.
- When rendering agent stages, preserve the current streaming behavior and do not regress to static completion-only updates.

---

## Folder structure

```
frontend/
├── app/
│   ├── layout.tsx
│   ├── page.tsx               # Main chat + dashboard page
│   ├── login/
│   │   └── page.tsx
│   └── api/
│       └── auth/
│           └── [...auth0]/
│               └── route.ts  # Auth0 Next.js handler
├── components/
│   ├── chat/
│   │   ├── ChatInput.tsx      # The main query input bar
│   │   └── ChatHistory.tsx    # Previous queries (optional)
│   ├── cards/
│   │   ├── ScheduleCard.tsx
│   │   ├── DiningCard.tsx
│   │   ├── EventsCard.tsx
│   │   ├── FinanceCard.tsx
│   │   ├── NavigatorCard.tsx
│   │   ├── StudyResourcesCard.tsx
│   │   └── JobsResearchCard.tsx
│   ├── dashboard/
│   │   └── Dashboard.tsx      # Renders whichever cards are non-null
│   └── ui/                    # ShadCN components live here
├── lib/
│   ├── api.ts                 # All fetch calls to the backend
│   └── types.ts               # TypeScript types mirroring the API contract
├── hooks/
│   └── useQuery.ts            # Handles loading/error state for API calls
├── public/
└── .env.local
```

---

## The API contract (read-only — do not change)

Person A's backend exposes one endpoint. You call it with the user's message and a Bearer token, and get back this shape:

```
POST https://<backend-url>/api/query
Authorization: Bearer <auth0_access_token>
Content-Type: application/json

{ "message": "I have an exam tomorrow and $20 for dinner" }
```

Response:

```json
{
  "query": "string",
  "agents_used": ["schedule", "dining", "finance"],
  "results": {
    "schedule": {
      "agent": "schedule",
      "study_blocks": [
        {
          "start": "HH:MM",
          "end": "HH:MM",
          "subject": "string",
          "type": "review|practice|reading"
        }
      ],
      "next_deadline": { "title": "string", "due": "ISO8601" }
    },
    "dining": {
      "agent": "dining",
      "options": [
        {
          "name": "string",
          "distance_min": 0,
          "budget_ok": true,
          "hours_open": true,
          "dietary_tags": []
        }
      ]
    },
    "events": {
      "agent": "events",
      "events": [
        {
          "title": "string",
          "location": "string",
          "start": "ISO8601",
          "free_food": false,
          "tags": []
        }
      ]
    },
    "finance": {
      "agent": "finance",
      "weekly_spent": 0.0,
      "budget_remaining": 0.0,
      "suggestion": "string"
    },
    "navigator": {
      "agent": "navigator",
      "origin": "string",
      "destination": "string",
      "walk_minutes": 0,
      "steps": ["string"],
      "map_url": "string"
    },
    "study_resources": {
      "agent": "study_resources",
      "tutoring": [
        {
          "service": "string",
          "subject": "string",
          "schedule": "string",
          "location": "string"
        }
      ],
      "office_hours": [
        {
          "professor": "string",
          "course": "string",
          "time": "string",
          "room": "string"
        }
      ]
    },
    "jobs_research": {
      "agent": "jobs_research",
      "jobs": [
        {
          "title": "string",
          "department": "string",
          "pay": "string",
          "apply_url": "string"
        }
      ],
      "labs": [
        {
          "pi": "string",
          "department": "string",
          "topic": "string",
          "contact": "string"
        }
      ],
      "cold_email": "string"
    }
  }
}
```

Any agent that wasn't triggered returns `null` for its key. Your `Dashboard` component must handle `null` gracefully — simply don't render that card.

---

## TypeScript types

Put these in `lib/types.ts`. These mirror the API contract exactly.

```typescript
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
  options: {
    name: string;
    distance_min: number;
    budget_ok: boolean;
    hours_open: boolean;
    dietary_tags: string[];
  }[];
}

export interface EventsResult {
  agent: "events";
  events: {
    title: string;
    location: string;
    start: string;
    free_food: boolean;
    tags: string[];
  }[];
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
  tutoring: {
    service: string;
    subject: string;
    schedule: string;
    location: string;
  }[];
  office_hours: {
    professor: string;
    course: string;
    time: string;
    room: string;
  }[];
}

export interface JobsResearchResult {
  agent: "jobs_research";
  jobs: { title: string; department: string; pay: string; apply_url: string }[];
  labs: { pi: string; department: string; topic: string; contact: string }[];
  cold_email: string;
}
```

---

## Mock data (use this until Person A's backend is ready)

Create `lib/mockData.ts` with this. Import it in `useQuery.ts` and return it instead of calling the real API when `NEXT_PUBLIC_USE_MOCK=true`.

```typescript
export const MOCK_RESPONSE: QueryResponse = {
  query: "I have an exam tomorrow and $20 for dinner",
  agents_used: ["schedule", "dining", "finance"],
  results: {
    schedule: {
      agent: "schedule",
      study_blocks: [
        { start: "18:00", end: "20:00", subject: "CMSC131", type: "review" },
        { start: "20:30", end: "22:00", subject: "CMSC131", type: "practice" },
      ],
      next_deadline: { title: "CMSC131 Exam", due: "2024-11-15T09:00:00" },
    },
    dining: {
      agent: "dining",
      options: [
        {
          name: "South Campus Dining",
          distance_min: 5,
          budget_ok: true,
          hours_open: true,
          dietary_tags: ["vegan", "halal"],
        },
        {
          name: "251 North",
          distance_min: 8,
          budget_ok: true,
          hours_open: true,
          dietary_tags: ["vegetarian"],
        },
      ],
    },
    finance: {
      agent: "finance",
      weekly_spent: 47.5,
      budget_remaining: 20.0,
      suggestion: "You're on track. $20 covers dinner at most dining halls.",
    },
    events: null,
    navigator: null,
    study_resources: null,
    jobs_research: null,
  },
};
```

---

## Component specs

### ChatInput.tsx

- Full-width text input bar, fixed at the bottom of the screen (like ChatGPT)
- "Send" button or Enter key to submit
- Shows a loading spinner while waiting for the API
- Disabled while loading
- On submit: calls `useQuery` hook with the message string

### Dashboard.tsx

- Receives the full `QueryResponse` object as a prop
- Renders a responsive card grid (CSS grid, 2 columns on desktop, 1 on mobile)
- Only renders a card if its result key is non-null
- Each card animates in with Framer Motion (`initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}`)
- Cards appear in this priority order: schedule → dining → finance → events → study_resources → navigator → jobs_research

### ScheduleCard.tsx

- Show `next_deadline` as a countdown at the top ("Exam in 14 hours")
- Render `study_blocks` as a mini timeline with subject labels and color coding by `type`
- Color coding: `review` = blue, `practice` = amber, `reading` = gray

### DiningCard.tsx

- List each dining option as a row
- Show green checkmark if `budget_ok`, red X if not
- Show "Open" badge if `hours_open`, "Closed" if not
- Show `dietary_tags` as small pills (color-coded)
- Show `distance_min` as "X min walk"

### EventsCard.tsx

- List upcoming events with time and location
- Highlight events with `free_food: true` with a special badge
- Show tags as pills

### FinanceCard.tsx

- Show a simple donut/bar chart of `weekly_spent` vs `budget_remaining` using Recharts
- Show `suggestion` as a quoted callout below the chart

### NavigatorCard.tsx

- Embed a Google Maps `<GoogleMap>` component showing the route
- Show `walk_minutes` prominently ("12 min walk")
- List `steps` as a numbered list below the map

### StudyResourcesCard.tsx

- Two sections: "Tutoring" and "Office hours"
- Each row shows service/professor, subject, time, location
- Keep it compact — this is reference info, not the focus

### JobsResearchCard.tsx

- Two tabs: "Campus jobs" and "Research labs"
- Each job row shows title, department, pay
- Each lab row shows PI name, topic, contact email
- If `cold_email` exists, show a "Copy email draft" button that copies to clipboard
- The email draft should appear in a collapsible section below the labs list

---

## Auth0 setup

Use `@auth0/nextjs-auth0` with Next.js App Router.

```typescript
// app/api/auth/[...auth0]/route.ts
import { handleAuth } from "@auth0/nextjs-auth0";
export const GET = handleAuth();
```

```typescript
// lib/api.ts — attach the access token to every backend request
import { getAccessToken } from "@auth0/nextjs-auth0";

export async function queryTerpAI(message: string): Promise<QueryResponse> {
  const { accessToken } = await getAccessToken();
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/query`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error("Query failed");
  return res.json();
}
```

Redirect unauthenticated users to `/login`. Wrap the main page in Auth0's `withPageAuthRequired` or the App Router equivalent.

---

## useQuery hook

```typescript
// hooks/useQuery.ts
import { useState } from "react";
import { queryTerpAI } from "@/lib/api";
import { QueryResponse } from "@/lib/types";

export function useQuery() {
  const [data, setData] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(message: string) {
    setLoading(true);
    setError(null);
    try {
      const result = await queryTerpAI(message);
      setData(result);
    } catch (e) {
      setError("Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return { data, loading, error, submit };
}
```

---

## UI/UX rules

- The page has two states: **empty** (just the chat input, centered) and **results** (chat input at bottom, dashboard above)
- Transition between states with Framer Motion layout animation
- Use ShadCN `Card` as the base for every agent card
- Use TailwindCSS only — no inline styles, no custom CSS files
- Responsive: 1 column on mobile, 2 columns on tablet, 2-3 columns on desktop
- Dark mode support via Tailwind's `dark:` prefix
- Loading state: show skeleton cards (ShadCN `Skeleton`) while waiting for the API
- Error state: show a toast notification (ShadCN `Toast`) with the error message
- Never show raw JSON to the user under any circumstances

---

## Build order (do these in sequence)

1. `npx create-next-app` + install all dependencies
2. `.env.local` with Auth0 and API URL vars
3. Auth0 login flow working end-to-end (login → redirect → protected page)
4. `lib/types.ts` — all TypeScript interfaces
5. `lib/mockData.ts` — mock response
6. `useQuery.ts` hook (using mock data first)
7. `ChatInput.tsx`
8. `Dashboard.tsx` with mock data rendering
9. Each card component, one at a time, against mock data
10. `lib/api.ts` — swap mock for real API once Person A's `/api/query` is live
11. Polish: Framer Motion animations, loading skeletons, responsive layout, dark mode

---

## Environment variables

```
NEXT_PUBLIC_API_URL=http://localhost:8000         # Person A's backend URL
NEXT_PUBLIC_USE_MOCK=true                         # Set to false when backend is ready
AUTH0_SECRET=
AUTH0_BASE_URL=http://localhost:3000
AUTH0_ISSUER_BASE_URL=https://your-tenant.us.auth0.com
AUTH0_CLIENT_ID=
AUTH0_CLIENT_SECRET=
AUTH0_AUDIENCE=https://terpai.api
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=
```

---

## Sync points with Person A

You don't need Person A to be done before you start. Work against mock data the whole time and only swap in the real API at the end. The sync moments are:

1. **Day 1**: Agree on the final JSON contract shape (already in this file — confirm it hasn't changed)
2. **Phase 3**: Person A exposes `/health` endpoint — confirm you can hit their server from your app
3. **Phase 4 end**: Person A's first real agent is live — test your DiningCard against it
4. **Phase 5**: All agents live — flip `NEXT_PUBLIC_USE_MOCK=false` and do a full end-to-end run

---

## Rules

- Every component must be in TypeScript — no `.jsx` files.
- Never call the backend directly from a component. Always go through `useQuery` or `lib/api.ts`.
- Never hardcode UMD-specific strings inside components — data comes from the API.
- Use ShadCN components for all UI primitives (buttons, cards, badges, inputs, skeletons, toasts). Don't build from scratch.
- Run `next lint` before committing. Fix all warnings, not just errors.
- Keep components under 150 lines. If a component grows past that, split it.
