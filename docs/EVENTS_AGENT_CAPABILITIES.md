# Events Agent - Complete Capability Documentation

## Overview

The **Events Agent** is a LangGraph-powered domain expert for discovering, filtering, and ranking events around UMD's campus. It intelligently extracts user preferences from natural language queries and surfaces the most relevant events with registration links.

---

## Core Capabilities

### 1. **Event Discovery**

The agent discovers events from multiple sources:

- **Campus Events** (UMD Calendar API or fallback database)
  - Official UMD calendar integration
  - Fallback to known UMD events (career fairs, movie nights, seminars, etc.)
  - Automatic event date/time extraction

- **Nearby Events** (Eventbrite API)
  - Events within College Park, MD area
  - Restaurant/venue-based social events
  - Integrated search by location (38.9869°N, -76.9426°W)
  - 8-second timeout with graceful fallback

---

### 2. **Natural Language Preference Extraction**

The agent automatically extracts from user messages:

#### **Event Category Detection**

Recognizes 17+ event types:

- `concert` - Music performances
- `seminar`, `lecture`, `workshop` - Academic events
- `conference`, `networking`, `career fair` - Professional events
- `social`, `party`, `dance` - Social gatherings
- `sports`, `festival`, `comedy`, `trivia`, `movie` - Entertainment
- `club fair`, `performance` - Student activities

**Example:** "Find a concert or networking event" → `["concert", "networking"]`

#### **Date Preference Extraction**

- `today` - Same day events
- `tomorrow` - Next day
- `this weekend` - Saturday/Sunday dates
- `next week` - 7 days ahead
- Any date term prioritizes matching events

**Example:** "Events this weekend" → `date_preference: "this weekend"`

#### **Time Preference Extraction**

- `morning` - 7 AM - 11 AM events
- `afternoon` - 12 PM - 4 PM events
- `evening` - 5 PM - 9 PM events
- `night` - 8 PM - 11 PM events

**Example:** "Tomorrow morning social event" → `time_preference: "morning"`

#### **Dietary Preference Detection**

- `vegan` / `plant-based` → `["vegan"]`
- `vegetarian` / `veg` → `["vegetarian"]`
- `halal` → `["halal"]`
- `gluten-free` / `gluten free` / `gf` → `["gluten-free"]`
- `kosher` → `["kosher"]`

**Note:** Used to filter event catering/food options

#### **Free Food Mention Detection**

Recognizes queries for food-inclusive events:

- "free food", "food", "snacks", "refreshments"
- Sets `free_food_only: True` → penalizes events without food
- Boosts free-food events with +1.0 to ranking score

---

### 3. **Intelligent Ranking System**

The agent ranks events with a weighted scoring algorithm:

| Factor            | Weight             | Notes                                          |
| ----------------- | ------------------ | ---------------------------------------------- |
| Category Match    | +3.0 pts per match | Highest priority                               |
| Date Match        | +2.0 pts           | Exact date match preferred                     |
| Time Match        | +1.5 pts per match | Morning/afternoon/evening preference           |
| Free Food         | +1.0 pts           | Bonus if event has food                        |
| Campus Events     | +0.5 pts           | Slight priority for on-campus                  |
| Free Food Penalty | -5.0 pts           | If user requested free food but event has none |

**Ranking Process:**

1. Scores each event independently
2. Sorts descending by score
3. Returns top 10 events

**Example:**

- Career fair (career match +3.0) + this weekend date (+2.0) + free food (+1.0) = **6.0 pts**
- Movie night (no match) + free food (+1.0) = **1.0 pts**
- Result: Career fair ranked first

---

### 4. **Event Registration & Links**

The agent builds registration links for each recommendation:

- **If Event Has URL:** Returns official registration link
- **If No URL:** Generates auto-formatted Google search link
  - Format: `https://www.google.com/search?q={event_name}+UMD+College+Park`
  - Example: `Engineering Career Fair` → `...q=Engineering+Career+Fair+UMD+College+Park`

---

### 5. **Context-Aware Follow-Up Questions**

The agent asks clarifying questions when needed:

- **Generic Query** (no category specified)
  - "What type of events are you interested in? (concert, career fair, social, etc.)"

- **No Date Preference**
  - "When do you want to attend? (today, tomorrow, this weekend, next week, etc.)"

- **Imprecise Time Request**
  - Prompts for morning/afternoon/evening/night clarification

- **Dietary/Food Constraints**
  - "Should I only show events with free food?"

These are returned in `follow_up_questions[]` when `needs_user_input: True`

---

## Response Schema

### **Top-Level Response**

```json
{
  "agent": "events",
  "options": [...],                              // Simplified event list
  "event_recommendations": [...],                // Detailed recommendations
  "recommendation_basis": {...},                 // Reasoning
  "needs_user_input": boolean,                   // Optional: asks for details
  "follow_up_questions": [...]                   // Optional: clarifying Qs
}
```

### **Options (Simplified)**

Each option in `options[]`:

```json
{
  "name": "Engineering Career Fair",
  "date": "2026-04-14",
  "time": "2:00 PM",
  "location": "Stamp Student Union, University of Maryland",
  "tags": ["career", "engineering", "networking"],
  "free_food": true
}
```

### **Event Recommendations (Detailed)**

Each recommendation in `event_recommendations[]`:

```json
{
  "name": "Engineering Career Fair",
  "date": "2026-04-14",
  "time": "2:00 PM",
  "location": "Stamp Student Union, University of Maryland",
  "category": "career",
  "free_food": true,
  "registration_url": "https://www.google.com/search?q=Engineering+Career+Fair+UMD+College+Park"
}
```

### **Recommendation Basis (Reasoning)**

```json
{
  "interested_categories": ["career", "networking"],
  "dietary_preferences": [],
  "date_preference": "this weekend",
  "time_preference": "afternoon",
  "free_food_only": true
}
```

This shows exactly what the agent extracted from the user query.

---

## Test Scenarios (8 Total)

### ✅ **Test 1: Extract Event Categories**

- Input: "I want to go to a concert or networking event this weekend"
- Validates: `interested_categories` contains extracted types
- Status: PASSING

### ✅ **Test 2: Filter by Free Food**

- Input: "Find events with free food this week"
- Validates: Free-food events ranked higher in `event_recommendations`
- Status: PASSING

### ✅ **Test 3: Extract Date Preferences**

- Input: "What's going on tomorrow evening?"
- Validates: `date_preference` and `time_preference` extracted correctly
- Status: PASSING

### ✅ **Test 4: Career Fair Priority**

- Input: "I'm looking for career development events"
- Validates: Career events ranked at top of recommendations
- Status: PASSING

### ✅ **Test 5: Prompt for Vague Queries**

- Input: "What events are there?"
- Validates: `needs_user_input: True` with clarifying questions
- Status: PASSING

### ✅ **Test 6: Build Registration Links**

- Input: "I want to attend a social event this weekend"
- Validates: Each recommendation has valid `registration_url` (HTTP link)
- Status: PASSING

### ✅ **Test 7: Extract Time Preferences**

- Input: "I prefer events in the morning"
- Validates: `time_preference: "morning"` in basis
- Status: PASSING

### ✅ **Test 8: Fallback on Failures**

- Input: Various queries
- Validates: Returns known events even if external APIs fail
- Status: PASSING

---

## LangGraph Workflow (6 Nodes)

```
ingest_context
     ↓
fetch_campus_events
     ↓
fetch_nearby_events
     ↓
rank_events
     ↓
build_registration_links
     ↓
build_result
     ↓
    END
```

### **Node Descriptions:**

1. **ingest_context**
   - Extracts: categories, dates, times, dietary prefs, free_food flag
   - Uses regex + keyword matching on user_message

2. **fetch_campus_events**
   - Calls UMD Calendar API or falls back to KNOWN_UMD_EVENTS dict
   - Returns list of ~5 campus events with details

3. **fetch_nearby_events**
   - Calls Eventbrite API (if EVENTBRITE_API_KEY set)
   - Returns ~5 nearby events or empty list if no API key

4. **rank_events**
   - Combines campus + nearby events
   - Scores each event based on user preferences
   - Returns top 10 sorted by score descending

5. **build_registration_links**
   - For each of top 5 events, generates registration URL
   - Stores in `registration_links` dict

6. **build_result**
   - Assembles final response with options, recommendations, basis
   - Determines if `needs_user_input` and generates follow_up_questions
   - Returns contract-compliant response

---

## Known UMD Events (Fallback Database)

```json
{
  "McKeldin Library Cleanup": {
    "date_offset_days": 0,
    "time": "11:00 AM",
    "location": "McKeldin Library, University of Maryland",
    "tags": ["club", "community service"],
    "free_food": false,
    "category": "community"
  },
  "Engineering Career Fair": {
    "date_offset_days": 3,
    "time": "2:00 PM",
    "location": "Stamp Student Union, University of Maryland",
    "tags": ["career", "engineering", "networking"],
    "free_food": true,
    "category": "career"
  },
  "Student Organization Fair": {
    "date_offset_days": 7,
    "time": "12:00 PM",
    "location": "Stamp Student Union, University of Maryland",
    "tags": ["student", "club"],
    "free_food": true,
    "category": "community"
  },
  "Campus Movie Night": {
    "date_offset_days": 2,
    "time": "8:00 PM",
    "location": "Nyumburu Cultural Center, University of Maryland",
    "tags": ["entertainment", "social"],
    "free_food": true,
    "category": "social"
  },
  "Mathematics Colloquium": {
    "date_offset_days": 4,
    "time": "3:30 PM",
    "location": "Mathematics Library, University of Maryland",
    "tags": ["academic", "lecture", "mathematics"],
    "free_food": false,
    "category": "academic"
  }
}
```

---

## Timeout & Fallback Behavior

- **LangGraph Execution:** 8-second timeout per node
- **API Calls:** 4-second timeout per request
- **On Failure:** Returns KNOWN_UMD_EVENTS ranked by preference
- **Graceful Degradation:** Missing external APIs don't crash the agent

---

## Environment Configuration

**Required (if using external APIs):**

- `EVENTBRITE_API_KEY` - Eventbrite API token for nearby events
- `UMD_DINING_API_KEY` - Optional UMD dining credentials

**Optional:**

- `UMD_CALENDAR_API_URL` - Custom UMD calendar endpoint

**Local Development:**

- Set `EVENTBRITE_API_KEY=""` to skip Eventbrite calls (always uses fallback)

---

## Integration with Task Planner

The **Task Planner** (Gemini AI) determines if the events agent should be invoked based on user message keywords:

**Activation Keywords:**

- "event", "concert", "movie", "seminar", "conference"
- "tonight", "this weekend", "tomorrow"
- "free time", "social"
- "activities", "what to do"

**Example Task Planner Output:**

```json
{
  "tasks": ["events"],
  "priority": "high",
  "context": {
    "event_type_mentioned": true,
    "date_mentioned": true,
    "location_mentioned": false
  }
}
```

---

## Summary

The **Events Agent** is a feature-complete domain expert that:

1. ✅ Discovers campus + nearby events
2. ✅ Extracts 5+ types of preferences from natural language
3. ✅ Intelligently ranks events using weighted scoring
4. ✅ Generates registration links
5. ✅ Asks clarifying follow-up questions
6. ✅ Gracefully handles external API failures
7. ✅ Returns consistent, contract-compliant responses
8. ✅ Fully tested with 8 scenario-based tests (all passing)

**Status:** ✅ PRODUCTION-READY (v1.0)

---
