# Health Resource Allocator

A full-stack application that generates a personalized, conflict-free health schedule for a client over a **3-month window**. The system manages multiple resources, prioritizes an action plan of activities (fitness, therapy, medications, meals, consultations), handles constraints like sleep and work hours, and dynamically adapts to travel plans with different adherence levels.

## Tech Stack

- **Backend:** Python 3.10+, FastAPI, Pydantic, Custom Scheduling Engine
- **Frontend:** React, TypeScript, Vite, React-Big-Calendar

## Project Structure

```text
├── backend/
│   ├── main.py             # FastAPI entry point
│   ├── models.py           # Core data schemas (dataclasses & enums)
│   ├── scheduler.py        # 4-Phase custom scheduling algorithm
│   ├── data_generator.py   # Generates 163+ activity variations from templates
│   ├── templates.json      # Source of truth for activities & resources
│   ├── tests/              # Unit tests (79 tests, 81% coverage)
│   └── data/               # Generated dataset and schedule cache
└── frontend/
    ├── src/
    │   ├── components/     # React components (Calendar, UnscheduledPanel)
    │   ├── hooks/          # Data fetching hooks
    │   ├── App.tsx         # Main layout
    │   └── types.ts        # TypeScript mirrors of Python models
```

## Running the Application

### 1. Backend Setup

The backend requires Python 3.10+ and serves the API on port 8000.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# (Optional) Regenerate the sample dataset
python data_generator.py

# Start the API server
uvicorn main:app --reload --port 8000
```

### 2. Frontend Setup

The frontend runs on Vite and serves the React application on port 5173.

```bash
cd frontend
npm install

# Start the development server
npm run dev
```

Visit `http://localhost:5173` in your browser to view the generated schedule.

### 3. Running Tests

```bash
cd backend
.venv/bin/python -m pytest tests/ -v
# With coverage:
.venv/bin/python -m pytest tests/ --cov=. --cov-report=term-missing
```

## Architecture

### Activity Model

Each `Activity` has:
- **`subtype`** — a string identifier (e.g., `"cardio"`, `"breakfast"`, `"med_0"`) that groups variants of the same concept. The scheduler uses subtypes to prevent two same-subtype activities from landing on the same day (subtype-spread policy).
- **`is_necessary`** — `True` for medications and meals, which are always included in the action plan and never skipped (except meals during `BREAK` travel).
- **`backup_activity_ids`** — a list of IDs of other activities that can substitute if the primary can't be scheduled on a given day. Backups must share the same subtype.

### Data Generation Pipeline

`data_generator.py` generates 163+ activity variations from `templates.json` and curates exactly **22 activities** into the action plan using these rules:

1. **Necessary subtypes** (those with `is_necessary: true`) — exactly 1 picked
2. **Optional subtypes** — filled greedily up to 22; up to 2 variants of the same optional subtype may be picked if both are non-daily and their combined weekly frequency ≤ 7.
3. **Backup wiring** — each action plan activity gets `backup_activity_ids` pointing to same-subtype variants not selected for the plan.

### 5-Phase Scheduling Algorithm

The scheduler (`scheduler.py`) processes the full 3-month window in 5 phases:

| Phase | What it does |
|-------|-------------|
| **Phase 1 — Meals** | Anchors breakfast, lunch, dinner at their `earliest_start`/`latest_start` windows |
| **Phase 2 — Medications** | Pins each medication relative to its `meal_relation` (BEFORE/WITH/AFTER a specific meal) |
| **Phase 3 — Priority** | Schedules remaining activities by priority, highest first, with immediate backup fallback |
| **Phase 4 — Week fallback** | For each week, tries to re-place unscheduled activities on other days in that 7-day window; then tries their backups on other days |
| **Phase 5 — Cross-day** | Scans the entire 3-month window for any remaining unscheduled activities and places them on days without a subtype collision |

### Constraint System

Every scheduling attempt checks:
- **Sleep block** — no activities during `sleep_start` → `sleep_end`
- **Work hours** — non-remote activities outside `work_start` → `work_end`
- **Overlap** — no two blocks overlap (travel day markers excluded)
- **Min gap** — required recovery gap after high-intensity activities
- **Transit buffer** — auto-calculated transit time when location changes
- **Subtype spread** — at most one activity per subtype per day (prevents double fitness sessions)
- **Weekly frequency** — each activity respects its `frequency_times` × `frequency_period` target

### Travel Adaptation

| Mode | Behaviour |
|------|-----------|
| `BREAK` | Only medications are scheduled; all other activities go to unscheduled |
| `FLEXIBLE` | Remote-capable activities are allowed; non-remote activities are skipped |
| `STRICT` | Full schedule maintained; travel destination treated as the activity location |

## Features

- **163+ activity variations** curated from templates into a 22-activity action plan
- **Automatic backup wiring** — same-subtype variants substitute when primaries can't fit
- **Subtype-spread policy** — prevents doubling-up on the same type of exercise in a day (e.g., two cardio sessions)
- **5-Phase scheduling** — meals anchor first, medications pin to meals, priority fill, week-level fallback, then cross-day recovery
- **3-month generation window** — covers a full 90-day horizon in a single schedule pass
- **Travel adaptation** — three distinct modes (BREAK, FLEXIBLE, STRICT)
- **Smart logistics** — prep times and transit buffers auto-calculated from location changes
- **Interactive UI** — glassmorphism dark-mode calendar with clickable detail views and an unscheduled sidebar
- **Type safe** — `mypy --strict` passes on all backend source files; `tsc --noEmit` passes on all frontend files


## Scheduler Performance

Validated across **100 random seeds** (1–100):

| Metric | Mean | Std Dev | Min | Max |
|---|---|---|---|---|
| Activities scheduled | 1467 | 12.4 | 1434 | 1501 |
| Activities unscheduled | 0.7 | 0.5 | 0 | 1 |
| Min fitness / weekday | 11.1 | 2.7 | 0 | 15 |
| Max fitness / weekday | 40.2 | 7.6 | 25 | 63 |

**Fitness distribution** (average across seeds):
  - MONDAY: 22
  - TUESDAY: 19
  - WEDNESDAY: 20
  - THURSDAY: 22
  - FRIDAY: 21
  - SATURDAY: 34
  - SUNDAY: 24

⚠️  Seeds with zero-fitness days: [19]

All 100 seeds produced ≤1 unscheduled activities (≤0.0% skip rate) with balanced weekday coverage.
