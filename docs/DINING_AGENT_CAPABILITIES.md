# Dining Agent Capabilities

The Dining Agent is a sophisticated LangGraph workflow designed to help students discover dining options based on budget, dietary preferences, location, and menu preferences. It seamlessly integrates both UMD campus dining and off-campus restaurants.

## Architecture

### 6-Node LangGraph Pipeline

```
1. Ingest Context      → Parse user query for constraints
2. Fetch Campus        → Query UMD dining API
3. Fetch Off-Campus    → Query OpenStreetMap Overpass API
4. Rank Options        → Score by preferences, budget
5. Build Route Preview → Calculate distance & maps link
6. Build Result        → Format unified response
```

## Core Capabilities

### 🏪 Dining Discovery

**Campus Dining:**

- 💡 Live UMD dining hall database (fetched from dining.umd.edu)
- 🔄 Fresh, maintained facility list
- 📍 Default: McKeldin Hall (if none specified)

**Off-Campus Restaurants:**

- 🌍 OpenStreetMap Overpass API for radius search
- 📊 2.2km radius from campus center by default
- 🏷️ Tags-based restaurant classification

### 💰 Budget Filtering

```
Extract budget from query: "$5", "under 10", "cheap", "expensive"
Campus: Menu item detection (salad, pizza, etc.) for price estimates
Off-campus: OSM tags → estimated cost tiers
```

**Supported Budget Tokens:**

- Exact amounts: "$5", "5 dollars"
- Ranges: "5-10", "under 15"
- Descriptive: "cheap", "expensive", "budget-friendly"

### 🥗 Dietary Filtering

```
vegan, vegetarian, halal, gluten-free, kosher
```

**Detection Methods:**

1. User query keywords
2. OSM restaurant tags for off-campus
3. Menu item matching (avoids incompatible menus)

### 🍽️ Menu Preferences

Recognizes keywords:

```
salad, bowl, chicken, pizza, burger, noodles, rice,
seafood, dessert, coffee, breakfast, lunch, dinner
```

### 📍 Location-Based Ranking

**Haversine Distance Calculation:**

- Great-circle distance accurate to meters
- Ranks options by proximity (nearest first)
- Weights budget + dietary match

**Ranking Formula:**

```
score = distance_penalty × budget_match × dietary_match × menu_match
```

### 🗺️ Route Preview

**Features:**

- Google Maps link generation
- Estimated distance in km
- Navigation URL: `https://maps.google.com/?q=`

## Query Examples

### Example 1: Budget-Conscious Student

```
Query: "Find me something cheap under McKeldin, I'm vegetarian"
→ Extracts: Budget=$low, Dietary=[vegetarian], Location=McKeldin
→ Returns: Top-ranked vegetarian options nearest McKeldin
```

### Example 2: Specific Menu Search

```
Query: "Looking for sushi near campus, budget $8-12"
→ Extracts: Budget=$8-12, Menu=[noodles, seafood], Location=campus
→ Returns: Sushi restaurants + campus options in budget
```

### Example 3: Adventurous Diner

```
Query: "Surprise me with halal food, I'll go anywhere"
→ Extracts: Dietary=[halal], Budget=unlimited, Location=all
→ Returns: Ranked halal options from entire surrounding area
```

## Input/Output Contracts

### Input (DiningState)

```python
{
    "message": str,           # User query
    "budget": float | None,   # Parsed budget
    "dietary": list[str],     # Dietary restrictions
    "menus": list[str],       # Menu preferences
    "location": str,          # Location constraint
    "options": list[dict],    # Accumulated options
    "route_links": dict,      # Route maps links
    "result": str             # Formatted result
}
```

### Output Format

```json
{
  "options": [
    {
      "name": "McKeldin Hall",
      "type": "campus",
      "estimated_cost": "$5-8",
      "dietary_options": ["vegetarian", "vegan"],
      "distance_km": 0.5,
      "maps_link": "https://maps.google.com/?q=McKeldin+Hall",
      "rating": 4.2
    },
    {
      "name": "Board & Brew College Park",
      "type": "off-campus",
      "estimated_cost": "$10-15",
      "dietary_options": ["halal"],
      "distance_km": 0.8,
      "maps_link": "https://maps.google.com/?q=...",
      "rating": 4.5
    }
  ],
  "summary": "Found 5 options matching your preferences...",
  "top_recommendation": "Board & Brew - nearest match for halal under $12"
}
```

## Data Sources

| Source        | Type       | Method          | Coverage         |
| ------------- | ---------- | --------------- | ---------------- |
| UMD Dining    | Campus     | din.umd.edu API | All campus halls |
| OpenStreetMap | Off-Campus | Overpass API    | 2.2km radius     |
| Google Maps   | Navigation | Link generation | Global           |

## Fallback Behavior

If query parsing fails or no options match:

1. Returns UMD dining halls with no filters
2. Provides off-campus restaurants in default radius
3. Suggests "Try again with more specific preferences"

## Performance Characteristics

- **Async Execution:** All network calls are async
- **Caching:** UMD dining names cached every 24h
- **Timeout:** 10s max per API call
- **Error Resilience:** Continues with partial results if one source fails

## Integration Points

- **Task Planner:** Triggered when query contains food/dining keywords
- **Router:** Runs asynchronously with other agents
- **Aggregator:** Results merged with events, finance, etc.

---

**Agent Type:** Domain Expert (LangGraph)  
**Model:** Gemini 3.1 Flash Lite  
**Language:** Python 3.11+  
**Framework:** FastAPI + LangGraph + Pydantic  
**Status:** ✅ Production Ready
