# Health Resource Allocator

A full-stack application that generates a personalized, conflict-free health schedule for a client over a 3-month window. The system manages multiple resources, prioritizes an action plan of activities (fitness, therapy, medications, meals, consultations), handles constraints like sleep and work, and dynamically adapts to travel plans with different adherence levels.

## Tech Stack

- **Backend:** Python, FastAPI, Pydantic, Custom Scheduling Engine
- **Frontend:** React, TypeScript, Vite, React-Big-Calendar
- **Data Source:** JSON-based templates and data generation

## Project Structure

```text
├── backend/
│   ├── main.py             # FastAPI entry point
│   ├── models.py           # Core data schemas (dataclasses & enums)
│   ├── scheduler.py        # 4-Phase custom scheduling algorithm
│   ├── data_generator.py   # Generates sample data from templates
│   ├── templates.json      # Source of truth for activities & resources
│   ├── tests/              # Unit tests
│   └── data/               # Generated schedule and dataset
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

## Features

- **4-Phase Scheduling Algorithm:** Anchors meals, pins medications to meals, prioritizes high-impact activities, and handles remaining activities based on availability.
- **Realistic Data Generation:** Curated action plan derived from 86 available variations, ensuring a balanced 25-activity plan.
- **Travel Adaptation:** Seamlessly adapts to `STRICT`, `FLEXIBLE`, and `BREAK` travel modes, utilizing backup remote activities when necessary.
- **Smart Logistics:** Automatically calculates prep times and transit buffers based on location.
- **Interactive UI:** Glassmorphism dark-mode React calendar with clickable detailed block views and an expandable sidebar for unscheduled activities.
- **Conflict Free:** Never schedules over sleep/work boundaries and ensures adequate gaps between intense activities.
