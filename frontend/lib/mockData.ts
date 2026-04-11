import { QueryResponse } from './types';

export const MOCK_RESPONSE: QueryResponse = {
  query: "I have an exam tomorrow and $20 for dinner",
  agents_used: ["schedule", "dining", "finance"],
  results: {
    schedule: {
      agent: "schedule",
      study_blocks: [
        { start: "14:00", end: "15:30", subject: "Biology", type: "review" },
        { start: "15:45", end: "17:00", subject: "Chemistry", type: "practice" },
        { start: "19:00", end: "20:30", subject: "Physics", type: "reading" }
      ],
      next_deadline: { title: "Biology Exam", due: "2026-04-12T09:00:00Z" }
    },
    dining: {
      agent: "dining",
      options: [
        { name: "McKeldin Dining Hall", distance_min: 5, budget_ok: true, hours_open: true, dietary_tags: ["vegetarian", "vegan"] },
        { name: "South Campus Café", distance_min: 8, budget_ok: true, hours_open: true, dietary_tags: ["gluten-free"] },
        { name: "The Board and Brew", distance_min: 12, budget_ok: false, hours_open: true, dietary_tags: ["nut-free"] }
      ]
    },
    events: {
      agent: "events",
      events: [
        { title: "Tech Talk: AI in 2026", location: "Stamp Student Center", start: "2026-04-12T16:00:00Z", free_food: true, tags: ["tech", "seminar"] },
        { title: "Spring Career Fair", location: "Xfinity Center", start: "2026-04-13T10:00:00Z", free_food: true, tags: ["jobs", "networking"] }
      ]
    },
    finance: {
      agent: "finance",
      weekly_spent: 85.50,
      budget_remaining: 14.50,
      suggestion: "You're close to your $100 weekly budget. Consider cooking meals at home to save money."
    },
    navigator: {
      agent: "navigator",
      origin: "Stamp Student Center",
      destination: "McKeldin Library",
      walk_minutes: 12,
      steps: [
        "Head north on Route 1",
        "Turn right on College Avenue",
        "Continue straight for 2 blocks",
        "Destination on your right"
      ],
      map_url: "https://maps.google.com"
    },
    study_resources: {
      agent: "study_resources",
      tutoring: [
        { service: "Biology Tutoring", subject: "Biology", schedule: "Mon/Wed 3-5pm", location: "McKeldin Library Room 201" },
        { service: "Chemistry Help Center", subject: "Chemistry", schedule: "Daily 10am-4pm", location: "Chemistry Building Room 105" }
      ],
      office_hours: [
        { professor: "Dr. Jane Smith", course: "BIO 101", time: "Tue/Thu 2-4pm", room: "Biology Building 310" },
        { professor: "Dr. John Doe", course: "CHEM 201", time: "Wed 1-3pm", room: "Chemistry Building 215" }
      ]
    },
    jobs_research: null
  }
};