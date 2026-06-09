# AGENT-MODIFIED: FastAPI application for Health Resource Allocator
"""
REST API serving the generated schedule to the React frontend.

Endpoints:
  GET /api/schedule       → Full 3-month schedule
  GET /api/activities     → All activities in the action plan
  GET /api/resources      → All resources
  GET /api/client         → Client profile with travel plans
  GET /api/health         → Health check
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, time, timedelta
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models import (
    Activity,
    ActivityType,
    ClientAvailability,
    DateException,
    DayOfWeek,
    FrequencyPeriod,
    MealRelation,
    MealType,
    Resource,
    ResourceAvailability,
    ResourceType,
    ScheduleBlockType,
    TimeSlot,
    TravelAdherence,
    TravelPlan,
)
from scheduler import generate_schedule

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Health Resource Allocator API",
    description="Generates personalized health schedules",
    version="1.0.0",
)

# CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════
#  DATA LOADING
# ═══════════════════════════════════════════════════════════

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _parse_time(t: str | None) -> time | None:
    """Parse a time string 'HH:MM' into a time object."""
    if t is None:
        return None
    parts = t.split(":")
    return time(int(parts[0]), int(parts[1]))


def _parse_date(d: str) -> date:
    """Parse an ISO date string into a date object."""
    return date.fromisoformat(d)


def load_activities() -> list[Activity]:
    """Load activities from action_plan.json."""
    with open(os.path.join(DATA_DIR, "action_plan.json")) as f:
        data = json.load(f)

    activities: list[Activity] = []
    for item in data["activities"]:
        activities.append(
            Activity(
                id=item["id"],
                name=item["name"],
                activity_type=ActivityType(item["activity_type"]),
                priority=item["priority"],
                duration_minutes=item["duration_minutes"],
                frequency_times=item["frequency_times"],
                frequency_period=FrequencyPeriod(item["frequency_period"]),
                details=item["details"],
                facilitator_id=item["facilitator_id"],
                facilitator_type=ResourceType(item["facilitator_type"]),
                location_id=item["location_id"],
                location_name=item["location_name"],
                remote_capable=item["remote_capable"],
                prep_description=item["prep_description"],
                prep_duration_minutes=item["prep_duration_minutes"],
                prep_buffer_minutes=item["prep_buffer_minutes"],
                backup_activity_ids=item["backup_activity_ids"],
                skip_adjustment=item["skip_adjustment"],
                metrics=item["metrics"],
                meal_relation=MealRelation(item["meal_relation"]),
                meal_relation_type=MealType(item["meal_relation_type"]),
                meal_relation_offset_minutes=item["meal_relation_offset_minutes"],
                earliest_start=_parse_time(item.get("earliest_start")),
                latest_start=_parse_time(item.get("latest_start")),
                preferred_days=[DayOfWeek(d) for d in item.get("preferred_days", [])],
                transit_minutes_from_home=item["transit_minutes_from_home"],
                min_gap_after_minutes=item["min_gap_after_minutes"],
                energy_cost=item["energy_cost"],
            )
        )

    return activities


def load_resources() -> list[Resource]:
    """Load resources from resources.json."""
    with open(os.path.join(DATA_DIR, "resources.json")) as f:
        data = json.load(f)

    return [
        Resource(
            id=item["id"],
            name=item["name"],
            resource_type=ResourceType(item["resource_type"]),
            specializations=item["specializations"],
            remote_capable=item["remote_capable"],
            location_id=item["location_id"],
        )
        for item in data["resources"]
    ]


def load_availability() -> list[ResourceAvailability]:
    """Load resource availability from availability.json."""
    with open(os.path.join(DATA_DIR, "availability.json")) as f:
        data = json.load(f)

    result: list[ResourceAvailability] = []
    for item in data["availability"]:
        result.append(
            ResourceAvailability(
                resource_id=item["resource_id"],
                recurring_slots=[
                    TimeSlot(
                        day_of_week=DayOfWeek(s["day_of_week"]),
                        start_time=_parse_time(s["start_time"]),  # type: ignore[arg-type]
                        end_time=_parse_time(s["end_time"]),  # type: ignore[arg-type]
                    )
                    for s in item["recurring_slots"]
                ],
                exceptions=[
                    DateException(
                        start_date=_parse_date(e["start_date"]),
                        end_date=_parse_date(e["end_date"]),
                        available=e["available"],
                        reason=e["reason"],
                    )
                    for e in item["exceptions"]
                ],
            )
        )

    return result


def load_client() -> ClientAvailability:
    """Load client availability from client.json."""
    with open(os.path.join(DATA_DIR, "client.json")) as f:
        data = json.load(f)

    return ClientAvailability(
        client_id=data["client_id"],
        home_location_id=data["home_location_id"],
        sleep_start=_parse_time(data["sleep_start"]),  # type: ignore[arg-type]
        sleep_end=_parse_time(data["sleep_end"]),  # type: ignore[arg-type]
        work_start=_parse_time(data.get("work_start")),
        work_end=_parse_time(data.get("work_end")),
        work_days=[DayOfWeek(d) for d in data.get("work_days", [])],
        recurring_slots=[
            TimeSlot(
                day_of_week=DayOfWeek(s["day_of_week"]),
                start_time=_parse_time(s["start_time"]),  # type: ignore[arg-type]
                end_time=_parse_time(s["end_time"]),  # type: ignore[arg-type]
            )
            for s in data["recurring_slots"]
        ],
        travel_plans=[
            TravelPlan(
                start_date=_parse_date(tp["start_date"]),
                end_date=_parse_date(tp["end_date"]),
                destination=tp["destination"],
                adherence=TravelAdherence(tp["adherence"]),
                has_gym_access=tp["has_gym_access"],
                has_kitchen_access=tp["has_kitchen_access"],
                remote_consultation_ok=tp["remote_consultation_ok"],
                available_equipment=tp["available_equipment"],
            )
            for tp in data["travel_plans"]
        ],
    )


# ═══════════════════════════════════════════════════════════
#  SCHEDULE SERIALIZATION
# ═══════════════════════════════════════════════════════════


def _serialize_time(t: time | None) -> str | None:
    """Serialize a time object to HH:MM."""
    if t is None:
        return None
    return t.strftime("%H:%M")


def _serialize_block(block: Any) -> dict[str, Any]:
    """Serialize a ScheduleBlock to a JSON-compatible dict."""
    return {
        "block_id": block.block_id,
        "block_type": block.block_type.value,
        "activity_id": block.activity_id,
        "activity_name": block.activity_name,
        "activity_type": block.activity_type.value if block.activity_type else None,
        "date": block.date.isoformat(),
        "start_time": _serialize_time(block.start_time),
        "end_time": _serialize_time(block.end_time),
        "facilitator_id": block.facilitator_id,
        "facilitator_name": block.facilitator_name,
        "location": block.location,
        "is_remote": block.is_remote,
        "is_backup": block.is_backup,
        "original_activity_id": block.original_activity_id,
        "metrics_to_collect": block.metrics_to_collect,
        "notes": block.notes,
        "color_code": block.color_code,
        "duration_minutes": block.duration_minutes,
    }


def _serialize_day(day: Any) -> dict[str, Any]:
    """Serialize a DaySchedule to a JSON-compatible dict."""
    return {
        "date": day.date.isoformat(),
        "day_of_week": day.day_of_week.value,
        "blocks": [_serialize_block(b) for b in day.blocks],
        "is_travel_day": day.is_travel_day,
        "travel_destination": day.travel_destination,
        "travel_adherence": day.travel_adherence.value if day.travel_adherence else None,
    }


def _serialize_unscheduled(item: Any) -> dict[str, Any]:
    """Serialize an UnscheduledActivity to a JSON-compatible dict."""
    return {
        "activity_id": item.activity_id,
        "activity_name": item.activity_name,
        "activity_type": item.activity_type.value,
        "target_date": item.target_date.isoformat(),
        "reason": item.reason,
        "adjustment": item.adjustment,
    }


# ═══════════════════════════════════════════════════════════
#  CACHED SCHEDULE
# ═══════════════════════════════════════════════════════════

_cached_schedule: dict[str, Any] | None = None


def _get_schedule() -> dict[str, Any]:
    """Generate or return cached schedule."""
    global _cached_schedule

    if _cached_schedule is not None:
        return _cached_schedule

    logger.info("Loading data and generating schedule...")

    activities = load_activities()
    resources = load_resources()
    availability = load_availability()
    client = load_client()

    start_date = date(2026, 6, 15)
    end_date = start_date + timedelta(days=90)

    schedule = generate_schedule(
        activities=activities,
        resources=resources,
        resource_availability=availability,
        client=client,
        start_date=start_date,
        end_date=end_date,
    )

    _cached_schedule = {
        "start_date": schedule.start_date.isoformat(),
        "end_date": schedule.end_date.isoformat(),
        "total_days": schedule.total_days,
        "total_scheduled": schedule.total_scheduled,
        "total_unscheduled": schedule.total_unscheduled,
        "days": [_serialize_day(d) for d in schedule.days],
        "unscheduled": [_serialize_unscheduled(u) for u in schedule.unscheduled],
    }

    logger.info(
        "Schedule generated: %d days, %d scheduled, %d unscheduled",
        schedule.total_days,
        schedule.total_scheduled,
        schedule.total_unscheduled,
    )

    return _cached_schedule


# ═══════════════════════════════════════════════════════════
#  API ENDPOINTS
# ═══════════════════════════════════════════════════════════


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "health-resource-allocator"}


@app.get("/api/schedule")
def get_schedule() -> dict[str, Any]:
    """
    Get the full 3-month schedule.

    Returns:
        Complete schedule with day-by-day blocks and unscheduled items.
    """
    return _get_schedule()


@app.get("/api/activities")
def get_activities() -> dict[str, Any]:
    """Get all activities from the action plan."""
    with open(os.path.join(DATA_DIR, "action_plan.json")) as f:
        return json.load(f)


@app.get("/api/resources")
def get_resources() -> dict[str, Any]:
    """Get all resources."""
    with open(os.path.join(DATA_DIR, "resources.json")) as f:
        return json.load(f)


@app.get("/api/client")
def get_client() -> dict[str, Any]:
    """Get client profile with travel plans."""
    with open(os.path.join(DATA_DIR, "client.json")) as f:
        return json.load(f)


@app.post("/api/schedule/regenerate")
def regenerate_schedule() -> dict[str, Any]:
    """
    Force regeneration of the schedule.

    Clears the cache and generates a fresh schedule.
    """
    global _cached_schedule
    _cached_schedule = None
    return _get_schedule()
