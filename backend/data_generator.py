# AGENT-MODIFIED: Data generator for Health Resource Allocator
"""
Generates realistic sample data for the Health Resource Allocator.

Produces:
  - action_plan.json:  100+ activities with priorities
  - resources.json:    25+ resources (specialists, trainers, equipment, locations)
  - availability.json: 3 months of resource availability
  - client.json:       Client profile with availability + travel plans

All data is derived from templates.json (the source of truth).
"""

from __future__ import annotations

import json
import os
import random
from datetime import date, time, timedelta
from typing import Any

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
    TimeSlot,
    TravelAdherence,
    TravelPlan,
)

# ═══════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════

SEED = 42
TEMPLATES_PATH = os.path.join(os.path.dirname(__file__), "templates.json")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data")

# Location name → location ID mapping
LOCATION_MAP: dict[str, str] = {
    "home": "loc_home",
    "gym": "loc_gym",
    "pool": "loc_pool",
    "clinic": "loc_clinic_a",
    "clinic_a": "loc_clinic_a",
    "clinic_b": "loc_clinic_b",
    "outdoors": "loc_outdoors",
}

# Schedule generation window
SCHEDULE_START = date(2026, 6, 15)
SCHEDULE_MONTHS = 3

# Day of week mapping
PYTHON_DOW_TO_ENUM: dict[int, DayOfWeek] = {
    0: DayOfWeek.MONDAY,
    1: DayOfWeek.TUESDAY,
    2: DayOfWeek.WEDNESDAY,
    3: DayOfWeek.THURSDAY,
    4: DayOfWeek.FRIDAY,
    5: DayOfWeek.SATURDAY,
    6: DayOfWeek.SUNDAY,
}


# ═══════════════════════════════════════════════════════════
#  TEMPLATE LOADING
# ═══════════════════════════════════════════════════════════


def load_templates() -> dict[str, Any]:
    """Load activity and resource templates from templates.json."""
    with open(TEMPLATES_PATH, "r") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════
#  RESOURCE GENERATION
# ═══════════════════════════════════════════════════════════


def generate_resources(templates: dict[str, Any]) -> list[Resource]:
    """
    Generate Resource objects from resource templates.

    Args:
        templates: The loaded templates.json data.

    Returns:
        List of Resource objects for all resource types.
    """
    resources: list[Resource] = []
    resource_templates = templates["resource_templates"]
    counter = 1

    for resource_type_str, items in resource_templates.items():
        resource_type = ResourceType(resource_type_str)
        for item in items:
            resource_id = item.get("id_override", f"res_{counter:03d}")
            resources.append(
                Resource(
                    id=resource_id,
                    name=item["name"],
                    resource_type=resource_type,
                    specializations=item.get("specializations", []),
                    remote_capable=item.get("remote_capable", False),
                    location_id=item.get("location_id"),
                )
            )
            counter += 1

    return resources


# ═══════════════════════════════════════════════════════════
#  ACTIVITY GENERATION
# ═══════════════════════════════════════════════════════════


def _find_facilitator(
    resources: list[Resource],
    facilitator_type_str: str,
    activity_name: str,
) -> tuple[str | None, ResourceType]:
    """
    Find a suitable facilitator from the resource list.

    Args:
        resources: All available resources.
        facilitator_type_str: The type of facilitator needed.
        activity_name: Activity name for matching specializations.

    Returns:
        Tuple of (facilitator_id, facilitator_type).
    """
    ftype = ResourceType(facilitator_type_str)
    if ftype == ResourceType.SELF:
        return None, ResourceType.SELF

    candidates = [r for r in resources if r.resource_type == ftype]
    if candidates:
        # Pick a random candidate
        chosen = random.choice(candidates)
        return chosen.id, ftype
    return None, ftype


def _parse_time(time_str: str) -> time:
    """Parse a time string like '07:00' into a time object."""
    parts = time_str.split(":")
    return time(int(parts[0]), int(parts[1]))


def generate_activities(
    templates: dict[str, Any],
    resources: list[Resource],
) -> list[Activity]:
    """
    Generate Activity objects from templates.

    The **action plan** (is_backup_only=False) contains ~25 curated activities:
      - 3 meal anchors
      - 8 medications
      - 5 fitness activities
      - 4 therapy/wellness activities
      - 2 consultations
      - 3 supplementary food/drink items

    All remaining activities (fitness variations, extra supplements, etc.)
    are created with is_backup_only=True so they remain available as
    backup/alternative references without being independently scheduled.

    Args:
        templates: The loaded templates.json data.
        resources: Generated resources for facilitator assignment.

    Returns:
        List of Activity objects sorted by priority.
    """
    activities: list[Activity] = []
    activity_templates = templates["activity_templates"]
    priority_counter = 1
    activity_counter = 1

    # ── Phase 1: Meal anchors (highest priority) ──────────────────
    food_templates = activity_templates.get("FOOD_CONSUMPTION", [])
    meal_anchors = [t for t in food_templates if t.get("is_meal_anchor", False)]
    non_meal_food = [t for t in food_templates if not t.get("is_meal_anchor", False)]

    for tmpl in meal_anchors:
        act_id = f"act_{activity_counter:03d}"
        fid, ftype = _find_facilitator(resources, tmpl["facilitator_type"], tmpl["name_template"])
        activities.append(_build_activity(
            act_id, tmpl["name_template"], ActivityType.FOOD_CONSUMPTION,
            priority_counter, tmpl, fid, ftype,
        ))
        activity_counter += 1
        priority_counter += 1

    # ── Phase 2: Medications ──────────────────────────────────────
    med_templates = activity_templates.get("MEDICATION", [])
    for tmpl in med_templates:
        act_id = f"act_{activity_counter:03d}"
        fid, ftype = _find_facilitator(resources, tmpl["facilitator_type"], tmpl["name_template"])
        act = _build_activity(
            act_id, tmpl["name_template"], ActivityType.MEDICATION,
            priority_counter, tmpl, fid, ftype,
        )
        act.meal_relation = MealRelation(tmpl.get("meal_relation", "NONE"))
        act.meal_relation_type = MealType(tmpl.get("meal_relation_type", "ANY"))
        act.meal_relation_offset_minutes = tmpl.get("meal_relation_offset_minutes", 0)
        activities.append(act)
        activity_counter += 1
        priority_counter += 1

    # ── Phase 3: Fitness (5 in action plan, rest backup-only) ─────
    fitness_templates = activity_templates.get("FITNESS", [])
    ACTION_PLAN_FITNESS = {
        "Zone 2 Run", "Strength Training - Upper Body",
        "Strength Training - Lower Body", "Morning Stretching",
        "Yoga - Flexibility",
    }
    FITNESS_FREQ: dict[str, tuple[int, FrequencyPeriod]] = {
        "Zone 2 Run": (3, FrequencyPeriod.WEEKLY),
        "HIIT Session": (2, FrequencyPeriod.WEEKLY),
        "Strength Training - Upper Body": (2, FrequencyPeriod.WEEKLY),
        "Strength Training - Lower Body": (2, FrequencyPeriod.WEEKLY),
        "Yoga - Flexibility": (2, FrequencyPeriod.WEEKLY),
        "Swimming Laps": (1, FrequencyPeriod.WEEKLY),
        "Morning Stretching": (7, FrequencyPeriod.DAILY),
        "Eye Exercises": (7, FrequencyPeriod.DAILY),
        "Cycling - Outdoor": (2, FrequencyPeriod.WEEKLY),
        "Core Stability Workout": (3, FrequencyPeriod.WEEKLY),
    }

    for tmpl in fitness_templates:
        act_id = f"act_{activity_counter:03d}"
        name = tmpl["name_template"]
        fid, ftype = _find_facilitator(resources, tmpl["facilitator_type"], name)
        freq, period = FITNESS_FREQ.get(name, (2, FrequencyPeriod.WEEKLY))
        act = _build_activity(act_id, name, ActivityType.FITNESS, priority_counter, tmpl, fid, ftype)
        act.frequency_times = freq
        act.frequency_period = period
        act.is_backup_only = name not in ACTION_PLAN_FITNESS
        activities.append(act)
        activity_counter += 1
        priority_counter += 1

    # ── Phase 4: Therapy (4 in action plan, rest backup-only) ─────
    therapy_templates = activity_templates.get("THERAPY", [])
    ACTION_PLAN_THERAPY = {"Guided Meditation", "Red Light Therapy", "Sports Massage", "Sauna Session"}
    THERAPY_FREQ: dict[str, tuple[int, FrequencyPeriod]] = {
        "Sauna Session": (2, FrequencyPeriod.WEEKLY),
        "Ice Bath / Cold Plunge": (1, FrequencyPeriod.WEEKLY),
        "Sports Massage": (1, FrequencyPeriod.WEEKLY),
        "Red Light Therapy": (3, FrequencyPeriod.WEEKLY),
        "Acupuncture Session": (1, FrequencyPeriod.WEEKLY),
        "Guided Meditation": (7, FrequencyPeriod.DAILY),
        "Breathwork Session": (3, FrequencyPeriod.WEEKLY),
    }

    for tmpl in therapy_templates:
        act_id = f"act_{activity_counter:03d}"
        name = tmpl["name_template"]
        fid, ftype = _find_facilitator(resources, tmpl["facilitator_type"], name)
        freq, period = THERAPY_FREQ.get(name, (2, FrequencyPeriod.WEEKLY))
        act = _build_activity(act_id, name, ActivityType.THERAPY, priority_counter, tmpl, fid, ftype)
        act.frequency_times = freq
        act.frequency_period = period
        act.is_backup_only = name not in ACTION_PLAN_THERAPY
        activities.append(act)
        activity_counter += 1
        priority_counter += 1

    # ── Phase 5: Consultations (2 in action plan) ─────────────────
    consult_templates = activity_templates.get("CONSULTATION", [])
    ACTION_PLAN_CONSULT = {"Physiotherapy Session", "Nutritionist Check-in"}
    CONSULT_CONF: dict[str, tuple[int, FrequencyPeriod]] = {
        "Cardiologist Review": (1, FrequencyPeriod.MONTHLY),
        "Nutritionist Check-in": (2, FrequencyPeriod.MONTHLY),
        "Physiotherapy Session": (1, FrequencyPeriod.WEEKLY),
        "Mental Health Check-in": (1, FrequencyPeriod.WEEKLY),
        "Dermatologist Review": (1, FrequencyPeriod.MONTHLY),
        "Sleep Specialist Review": (1, FrequencyPeriod.MONTHLY),
    }

    for tmpl in consult_templates:
        act_id = f"act_{activity_counter:03d}"
        name = tmpl["name_template"]
        fid, ftype = _find_facilitator(resources, tmpl["facilitator_type"], name)
        freq, period = CONSULT_CONF.get(name, (1, FrequencyPeriod.MONTHLY))
        act = _build_activity(act_id, name, ActivityType.CONSULTATION, priority_counter, tmpl, fid, ftype)
        act.frequency_times = freq
        act.frequency_period = period
        act.is_backup_only = name not in ACTION_PLAN_CONSULT
        activities.append(act)
        activity_counter += 1
        priority_counter += 1

    # ── Phase 6: Supplementary food (3 in action plan) ────────────
    ACTION_PLAN_FOOD = {"Hydration Check", "Afternoon Protein Shake", "Mid-Morning Snack"}
    for tmpl in non_meal_food:
        act_id = f"act_{activity_counter:03d}"
        name = tmpl["name_template"]
        fid, ftype = _find_facilitator(resources, tmpl["facilitator_type"], name)
        freq_times = 3 if "Hydration" in name else 1
        freq_period = FrequencyPeriod.WEEKLY if "Meal Prep" in name else FrequencyPeriod.DAILY
        act = _build_activity(act_id, name, ActivityType.FOOD_CONSUMPTION, priority_counter, tmpl, fid, ftype)
        act.frequency_times = freq_times
        act.frequency_period = freq_period
        act.is_backup_only = name not in ACTION_PLAN_FOOD
        activities.append(act)
        activity_counter += 1
        priority_counter += 1

    # ── Phase 7: Fitness variations (backup-only) ─────────────────
    variation_suffixes = [("- Beginner", 0.7), ("- Advanced", 1.3), ("- Quick", 0.5)]
    base_fitness = [a for a in activities if a.activity_type == ActivityType.FITNESS and not a.is_backup_only]

    for act in base_fitness:
        for suffix, dur_mult in variation_suffixes:
            act_id = f"act_{activity_counter:03d}"
            activities.append(Activity(
                id=act_id,
                name=f"{act.name} {suffix}",
                activity_type=ActivityType.FITNESS,
                priority=priority_counter,
                duration_minutes=max(10, int(act.duration_minutes * dur_mult)),
                frequency_times=max(1, act.frequency_times - 1),
                frequency_period=act.frequency_period,
                details=f"{act.details} ({suffix.strip('- ')} variation)",
                facilitator_id=act.facilitator_id,
                facilitator_type=act.facilitator_type,
                location_id=act.location_id,
                location_name=act.location_name,
                remote_capable=act.remote_capable,
                prep_description=act.prep_description,
                prep_duration_minutes=act.prep_duration_minutes,
                prep_buffer_minutes=act.prep_buffer_minutes,
                backup_activity_ids=[act.id],
                skip_adjustment=act.skip_adjustment,
                metrics=act.metrics,
                earliest_start=act.earliest_start,
                latest_start=act.latest_start,
                transit_minutes_from_home=act.transit_minutes_from_home,
                min_gap_after_minutes=act.min_gap_after_minutes,
                energy_cost=max(1, min(5, act.energy_cost + (1 if "Advanced" in suffix else -1))),
                is_backup_only=True,
            ))
            activity_counter += 1
            priority_counter += 1

    # ── Phase 8: Extra backup-only activities ─────────────────────
    _extras = [
        ("Resistance Band Workout", ActivityType.FITNESS, 25, "home", True, 2, "06:00", "20:00"),
        ("Foam Rolling Recovery", ActivityType.FITNESS, 15, "home", True, 1, "06:00", "21:00"),
        ("Mobility Flow", ActivityType.FITNESS, 20, "home", True, 1, "06:00", "21:00"),
        ("Epsom Salt Bath", ActivityType.THERAPY, 25, "home", False, 1, "19:00", "21:30"),
        ("Gratitude Journaling", ActivityType.THERAPY, 10, "home", True, 1, "06:00", "22:00"),
    ]
    for name, atype, dur, loc, remote, energy, earliest, latest in _extras:
        act_id = f"act_{activity_counter:03d}"
        activities.append(Activity(
            id=act_id, name=name, activity_type=atype,
            priority=priority_counter, duration_minutes=dur,
            frequency_times=1, frequency_period=FrequencyPeriod.DAILY,
            details=name, facilitator_id=None, facilitator_type=ResourceType.SELF,
            location_id=LOCATION_MAP.get(loc), location_name=loc,
            remote_capable=remote, prep_description="", prep_duration_minutes=0,
            prep_buffer_minutes=0, skip_adjustment="Resume next day",
            metrics=["session_completed"],
            earliest_start=_parse_time(earliest), latest_start=_parse_time(latest),
            transit_minutes_from_home=0, min_gap_after_minutes=5,
            energy_cost=energy, is_backup_only=True,
        ))
        activity_counter += 1
        priority_counter += 1

    # ── Cross-reference backups ───────────────────────────────────
    _set_backups(activities, "Zone 2 Run", ["Cycling - Outdoor", "Resistance Band Workout"])
    _set_backups(activities, "Strength Training - Upper Body", ["Resistance Band Workout"])
    _set_backups(activities, "Strength Training - Lower Body", ["Yoga - Flexibility"])
    _set_backups(activities, "Yoga - Flexibility", ["Mobility Flow", "Morning Stretching"])
    _set_backups(activities, "Morning Stretching", ["Mobility Flow"])
    _set_backups(activities, "Sauna Session", ["Red Light Therapy", "Epsom Salt Bath"])
    _set_backups(activities, "Sports Massage", ["Foam Rolling Recovery", "Mobility Flow"])
    _set_backups(activities, "Guided Meditation", ["Gratitude Journaling"])

    activities.sort(key=lambda a: a.priority)
    return activities


def _build_activity(
    act_id: str,
    name: str,
    act_type: ActivityType,
    priority: int,
    tmpl: dict[str, Any],
    facilitator_id: str | None,
    facilitator_type: ResourceType,
) -> Activity:
    """Build an Activity from a template dict — reduces boilerplate."""
    return Activity(
        id=act_id,
        name=name,
        activity_type=act_type,
        priority=priority,
        duration_minutes=tmpl["duration_minutes"],
        frequency_times=1,
        frequency_period=FrequencyPeriod.DAILY,
        details=tmpl["details"],
        facilitator_id=facilitator_id,
        facilitator_type=facilitator_type,
        location_id=LOCATION_MAP.get(tmpl["location_name"]),
        location_name=tmpl["location_name"],
        remote_capable=tmpl["remote_capable"],
        prep_description=tmpl.get("prep_description", ""),
        prep_duration_minutes=tmpl.get("prep_duration_minutes", 0),
        prep_buffer_minutes=tmpl.get("prep_buffer_minutes", 0),
        skip_adjustment=tmpl.get("skip_adjustment", ""),
        metrics=tmpl.get("metrics", []),
        earliest_start=_parse_time(tmpl["earliest_start"]) if "earliest_start" in tmpl else None,
        latest_start=_parse_time(tmpl["latest_start"]) if "latest_start" in tmpl else None,
        transit_minutes_from_home=tmpl.get("transit_minutes_from_home", 0),
        min_gap_after_minutes=tmpl.get("min_gap_after_minutes", 0),
        energy_cost=tmpl.get("energy_cost", 1),
    )








def _set_backups(
    activities: list[Activity],
    activity_name: str,
    backup_names: list[str],
) -> None:
    """
    Set backup activity IDs on an activity by name.

    Args:
        activities: All generated activities.
        activity_name: Name of the activity to set backups for.
        backup_names: Names of backup activities.
    """
    target = next((a for a in activities if a.name == activity_name), None)
    if not target:
        return

    backup_ids: list[str] = []
    for bname in backup_names:
        backup = next((a for a in activities if a.name == bname), None)
        if backup:
            backup_ids.append(backup.id)

    if backup_ids:
        target.backup_activity_ids = backup_ids


# ═══════════════════════════════════════════════════════════
#  AVAILABILITY GENERATION
# ═══════════════════════════════════════════════════════════


def generate_resource_availability(
    resources: list[Resource],
    start_date: date,
    months: int = 3,
) -> list[ResourceAvailability]:
    """
    Generate 3 months of availability data for all resources.

    Each resource gets a recurring weekly schedule with 10-15%
    of dates having exceptions (holidays, conferences, etc.).

    Args:
        resources: All resources to generate availability for.
        start_date: Start of the availability window.
        months: Number of months to generate.

    Returns:
        List of ResourceAvailability objects.
    """
    end_date = start_date + timedelta(days=months * 30)
    availabilities: list[ResourceAvailability] = []

    exception_reasons = [
        "Holiday", "Conference", "Training", "Personal day",
        "Equipment maintenance", "Facility closed", "Vacation",
    ]

    for resource in resources:
        # Skip LOCATION and SELF types — they don't have availability
        if resource.resource_type in (ResourceType.LOCATION, ResourceType.SELF):
            continue

        # Generate recurring weekly schedule based on resource type
        recurring: list[TimeSlot] = []

        if resource.resource_type == ResourceType.EQUIPMENT:
            # Equipment available most of the day, every day
            for dow in DayOfWeek:
                recurring.append(
                    TimeSlot(day_of_week=dow, start_time=time(6, 0), end_time=time(22, 0))
                )
        elif resource.resource_type == ResourceType.TRAINER:
            # Trainers work Mon-Sat, split shifts
            for dow in [DayOfWeek.MONDAY, DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY,
                        DayOfWeek.THURSDAY, DayOfWeek.FRIDAY]:
                recurring.append(
                    TimeSlot(day_of_week=dow, start_time=time(6, 0), end_time=time(12, 0))
                )
                recurring.append(
                    TimeSlot(day_of_week=dow, start_time=time(16, 0), end_time=time(20, 0))
                )
            recurring.append(
                TimeSlot(day_of_week=DayOfWeek.SATURDAY, start_time=time(8, 0), end_time=time(13, 0))
            )
        else:
            # Specialists and Allied Health: Mon-Fri, office hours
            for dow in [DayOfWeek.MONDAY, DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY,
                        DayOfWeek.THURSDAY, DayOfWeek.FRIDAY]:
                recurring.append(
                    TimeSlot(day_of_week=dow, start_time=time(9, 0), end_time=time(17, 0))
                )

        # Generate exceptions (10-15% of days)
        exceptions: list[DateException] = []
        total_days = (end_date - start_date).days
        num_exceptions = random.randint(
            int(total_days * 0.05),
            int(total_days * 0.12),
        )

        used_dates: set[date] = set()
        for _ in range(num_exceptions):
            exc_start = start_date + timedelta(days=random.randint(0, total_days - 1))
            if exc_start in used_dates:
                continue
            used_dates.add(exc_start)

            # Most exceptions are 1 day, some are 2-5 days
            exc_duration = random.choices([1, 2, 3, 5], weights=[60, 20, 15, 5])[0]
            exc_end = exc_start + timedelta(days=exc_duration - 1)

            exceptions.append(
                DateException(
                    start_date=exc_start,
                    end_date=exc_end,
                    available=False,
                    reason=random.choice(exception_reasons),
                )
            )

        availabilities.append(
            ResourceAvailability(
                resource_id=resource.id,
                recurring_slots=recurring,
                exceptions=exceptions,
            )
        )

    return availabilities


def generate_client_availability(start_date: date) -> ClientAvailability:
    """
    Generate client availability profile with travel plans.

    Args:
        start_date: Start of the schedule window.

    Returns:
        ClientAvailability with recurring slots and 3 travel plans.
    """
    # Client is available from 6 AM to 10:30 PM every day
    recurring: list[TimeSlot] = []
    for dow in DayOfWeek:
        recurring.append(
            TimeSlot(day_of_week=dow, start_time=time(6, 0), end_time=time(22, 30))
        )

    # Generate 3 travel plans at different adherence levels
    travel_plans = [
        TravelPlan(
            start_date=start_date + timedelta(days=15),
            end_date=start_date + timedelta(days=19),
            destination="New York City",
            adherence=TravelAdherence.STRICT,
            has_gym_access=True,
            has_kitchen_access=False,
            remote_consultation_ok=True,
            available_equipment=[],
        ),
        TravelPlan(
            start_date=start_date + timedelta(days=40),
            end_date=start_date + timedelta(days=46),
            destination="Bali, Indonesia",
            adherence=TravelAdherence.FLEXIBLE,
            has_gym_access=True,
            has_kitchen_access=True,
            remote_consultation_ok=True,
            available_equipment=[],
        ),
        TravelPlan(
            start_date=start_date + timedelta(days=70),
            end_date=start_date + timedelta(days=72),
            destination="Lake Tahoe",
            adherence=TravelAdherence.BREAK,
            has_gym_access=False,
            has_kitchen_access=True,
            remote_consultation_ok=False,
            available_equipment=[],
        ),
    ]

    return ClientAvailability(
        client_id="client_001",
        recurring_slots=recurring,
        travel_plans=travel_plans,
        home_location_id="loc_home",
        sleep_start=time(22, 30),
        sleep_end=time(6, 0),
        work_start=time(9, 0),
        work_end=time(17, 0),
        work_days=[
            DayOfWeek.MONDAY,
            DayOfWeek.TUESDAY,
            DayOfWeek.WEDNESDAY,
            DayOfWeek.THURSDAY,
            DayOfWeek.FRIDAY,
        ],
    )


# ═══════════════════════════════════════════════════════════
#  SERIALIZATION
# ═══════════════════════════════════════════════════════════


def _serialize_time(t: time | None) -> str | None:
    """Serialize a time object to HH:MM string."""
    if t is None:
        return None
    return t.strftime("%H:%M")


def _serialize_date(d: date) -> str:
    """Serialize a date object to ISO format string."""
    return d.isoformat()


def _serialize_activity(act: Activity) -> dict[str, Any]:
    """Serialize an Activity to a JSON-compatible dict."""
    return {
        "id": act.id,
        "name": act.name,
        "activity_type": act.activity_type.value,
        "priority": act.priority,
        "duration_minutes": act.duration_minutes,
        "frequency_times": act.frequency_times,
        "frequency_period": act.frequency_period.value,
        "details": act.details,
        "facilitator_id": act.facilitator_id,
        "facilitator_type": act.facilitator_type.value,
        "location_id": act.location_id,
        "location_name": act.location_name,
        "remote_capable": act.remote_capable,
        "prep_description": act.prep_description,
        "prep_duration_minutes": act.prep_duration_minutes,
        "prep_buffer_minutes": act.prep_buffer_minutes,
        "backup_activity_ids": act.backup_activity_ids,
        "skip_adjustment": act.skip_adjustment,
        "metrics": act.metrics,
        "meal_relation": act.meal_relation.value,
        "meal_relation_type": act.meal_relation_type.value,
        "meal_relation_offset_minutes": act.meal_relation_offset_minutes,
        "earliest_start": _serialize_time(act.earliest_start),
        "latest_start": _serialize_time(act.latest_start),
        "preferred_days": [d.value for d in act.preferred_days],
        "transit_minutes_from_home": act.transit_minutes_from_home,
        "min_gap_after_minutes": act.min_gap_after_minutes,
        "energy_cost": act.energy_cost,
    }


def _serialize_resource(res: Resource) -> dict[str, Any]:
    """Serialize a Resource to a JSON-compatible dict."""
    return {
        "id": res.id,
        "name": res.name,
        "resource_type": res.resource_type.value,
        "specializations": res.specializations,
        "remote_capable": res.remote_capable,
        "location_id": res.location_id,
    }


def _serialize_availability(avail: ResourceAvailability) -> dict[str, Any]:
    """Serialize ResourceAvailability to a JSON-compatible dict."""
    return {
        "resource_id": avail.resource_id,
        "recurring_slots": [
            {
                "day_of_week": slot.day_of_week.value,
                "start_time": _serialize_time(slot.start_time),
                "end_time": _serialize_time(slot.end_time),
            }
            for slot in avail.recurring_slots
        ],
        "exceptions": [
            {
                "start_date": _serialize_date(exc.start_date),
                "end_date": _serialize_date(exc.end_date),
                "available": exc.available,
                "reason": exc.reason,
            }
            for exc in avail.exceptions
        ],
    }


def _serialize_client(client: ClientAvailability) -> dict[str, Any]:
    """Serialize ClientAvailability to a JSON-compatible dict."""
    return {
        "client_id": client.client_id,
        "home_location_id": client.home_location_id,
        "sleep_start": _serialize_time(client.sleep_start),
        "sleep_end": _serialize_time(client.sleep_end),
        "work_start": _serialize_time(client.work_start),
        "work_end": _serialize_time(client.work_end),
        "work_days": [d.value for d in client.work_days],
        "recurring_slots": [
            {
                "day_of_week": slot.day_of_week.value,
                "start_time": _serialize_time(slot.start_time),
                "end_time": _serialize_time(slot.end_time),
            }
            for slot in client.recurring_slots
        ],
        "travel_plans": [
            {
                "start_date": _serialize_date(tp.start_date),
                "end_date": _serialize_date(tp.end_date),
                "destination": tp.destination,
                "adherence": tp.adherence.value,
                "has_gym_access": tp.has_gym_access,
                "has_kitchen_access": tp.has_kitchen_access,
                "remote_consultation_ok": tp.remote_consultation_ok,
                "available_equipment": tp.available_equipment,
            }
            for tp in client.travel_plans
        ],
    }


# ═══════════════════════════════════════════════════════════
#  MAIN GENERATION PIPELINE
# ═══════════════════════════════════════════════════════════


def generate_all_data() -> None:
    """
    Generate all sample data and write to backend/data/ directory.

    Creates:
      - data/action_plan.json
      - data/resources.json
      - data/availability.json
      - data/client.json
    """
    random.seed(SEED)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Loading templates...")
    templates = load_templates()

    print("Generating resources...")
    resources = generate_resources(templates)
    print(f"  → {len(resources)} resources generated")

    print("Generating activities...")
    activities = generate_activities(templates, resources)
    print(f"  → {len(activities)} activities generated")

    print("Generating resource availability (3 months)...")
    availability = generate_resource_availability(resources, SCHEDULE_START)
    print(f"  → {len(availability)} resource schedules generated")

    print("Generating client availability...")
    client = generate_client_availability(SCHEDULE_START)
    print(f"  → Client with {len(client.travel_plans)} travel plans")

    # Write files
    action_plan_path = os.path.join(OUTPUT_DIR, "action_plan.json")
    with open(action_plan_path, "w") as f:
        json.dump(
            {"activities": [_serialize_activity(a) for a in activities]},
            f,
            indent=2,
        )
    print(f"  ✓ {action_plan_path}")

    resources_path = os.path.join(OUTPUT_DIR, "resources.json")
    with open(resources_path, "w") as f:
        json.dump(
            {"resources": [_serialize_resource(r) for r in resources]},
            f,
            indent=2,
        )
    print(f"  ✓ {resources_path}")

    availability_path = os.path.join(OUTPUT_DIR, "availability.json")
    with open(availability_path, "w") as f:
        json.dump(
            {"availability": [_serialize_availability(a) for a in availability]},
            f,
            indent=2,
        )
    print(f"  ✓ {availability_path}")

    client_path = os.path.join(OUTPUT_DIR, "client.json")
    with open(client_path, "w") as f:
        json.dump(_serialize_client(client), f, indent=2)
    print(f"  ✓ {client_path}")

    print(f"\n✅ All data generated successfully! ({len(activities)} activities total)")


if __name__ == "__main__":
    generate_all_data()
