# AGENT-MODIFIED: Full data model for Health Resource Allocator
"""
Core data models for the Health Resource Allocator.

All data structures are defined here as @dataclass types.
This is the single source of truth for data shapes — TypeScript
types in the frontend must mirror these exactly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, time
from enum import Enum
from typing import Optional


# ═══════════════════════════════════════════════════════════
#  ENUMS
# ═══════════════════════════════════════════════════════════


class ActivityType(str, Enum):
    """The 5 distinct health activity types."""

    FITNESS = "FITNESS"
    FOOD_CONSUMPTION = "FOOD_CONSUMPTION"
    MEDICATION = "MEDICATION"
    THERAPY = "THERAPY"
    CONSULTATION = "CONSULTATION"


class ResourceType(str, Enum):
    """Types of resources / facilitators."""

    SPECIALIST = "SPECIALIST"
    ALLIED_HEALTH = "ALLIED_HEALTH"
    TRAINER = "TRAINER"
    EQUIPMENT = "EQUIPMENT"
    LOCATION = "LOCATION"
    SELF = "SELF"


class FrequencyPeriod(str, Enum):
    """The period over which an activity's frequency is measured."""

    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class DayOfWeek(str, Enum):
    """Days of the week."""

    MONDAY = "MONDAY"
    TUESDAY = "TUESDAY"
    WEDNESDAY = "WEDNESDAY"
    THURSDAY = "THURSDAY"
    FRIDAY = "FRIDAY"
    SATURDAY = "SATURDAY"
    SUNDAY = "SUNDAY"


class MealRelation(str, Enum):
    """How a medication relates to a meal."""

    BEFORE_MEAL = "BEFORE_MEAL"
    AFTER_MEAL = "AFTER_MEAL"
    WITH_MEAL = "WITH_MEAL"
    NONE = "NONE"


class MealType(str, Enum):
    """Which specific meal a medication is tied to."""

    BREAKFAST = "BREAKFAST"
    LUNCH = "LUNCH"
    DINNER = "DINNER"
    ANY = "ANY"


class TravelAdherence(str, Enum):
    """
    How strictly the client wants to follow the plan during travel.

    STRICT   – Schedule everything possible; try remote backups for non-remote.
    FLEXIBLE – Only high-priority + remote-capable activities.
    BREAK    – Only medications (never skippable, even on break).
    """

    STRICT = "STRICT"
    FLEXIBLE = "FLEXIBLE"
    BREAK = "BREAK"


class ScheduleBlockType(str, Enum):
    """Type of block in the final schedule."""

    ACTIVITY = "ACTIVITY"
    PREP = "PREP"
    TRANSIT = "TRANSIT"
    TRAVEL_DAY = "TRAVEL_DAY"


# ═══════════════════════════════════════════════════════════
#  ACTIVITY (Action Plan Item)
# ═══════════════════════════════════════════════════════════


@dataclass
class Activity:
    """
    A single health activity from the action plan.

    Carries all 10 properties from the spec, plus duration,
    transit info, and scheduling metadata.
    """

    # Identity
    id: str
    name: str
    activity_type: ActivityType
    priority: int  # Lower number = higher priority

    # Property 1: Duration
    duration_minutes: int

    # Property 2: Frequency
    frequency_times: int
    frequency_period: FrequencyPeriod

    # Property 3: Details
    details: str

    # Property 4: Facilitator
    facilitator_id: Optional[str]
    facilitator_type: ResourceType

    # Property 5: Location
    location_id: Optional[str]
    location_name: str  # "home", "gym", "clinic", etc.

    # Property 6: Remote capability
    remote_capable: bool

    # Property 7: Prep requirements
    prep_description: str
    prep_duration_minutes: int  # 0 = no prep
    prep_buffer_minutes: int  # Min gap between prep end and activity start

    # Property 8: Backup / substitute activities
    backup_activity_ids: list[str] = field(default_factory=list)

    # Property 9: Skip adjustments
    skip_adjustment: str = ""

    # Property 10: Metrics to collect
    metrics: list[str] = field(default_factory=list)

    # Medication ↔ Meal relationship
    meal_relation: MealRelation = MealRelation.NONE
    meal_relation_type: MealType = MealType.ANY
    meal_relation_offset_minutes: int = 0

    # Time-of-day constraints (configurable per activity)
    earliest_start: Optional[time] = None
    latest_start: Optional[time] = None
    preferred_days: list[DayOfWeek] = field(default_factory=list)

    # Transit
    transit_minutes_from_home: int = 0  # 0 for home-based activities

    # Scheduling metadata
    min_gap_after_minutes: int = 0
    energy_cost: int = 1  # 1-5 scale (for future intensity balancing)

    # Whether this activity is only a backup/alternative (not independently scheduled)
    is_backup_only: bool = False


# ═══════════════════════════════════════════════════════════
#  RESOURCES
# ═══════════════════════════════════════════════════════════


@dataclass
class Resource:
    """A resource that can facilitate or support activities."""

    id: str
    name: str
    resource_type: ResourceType
    specializations: list[str] = field(default_factory=list)
    remote_capable: bool = False
    location_id: Optional[str] = None


# ═══════════════════════════════════════════════════════════
#  AVAILABILITY
# ═══════════════════════════════════════════════════════════


@dataclass
class TimeSlot:
    """A recurring time window on a specific day of the week."""

    day_of_week: DayOfWeek
    start_time: time
    end_time: time


@dataclass
class DateException:
    """A specific date range where availability differs from the norm."""

    start_date: date
    end_date: date
    available: bool  # False = blocked, True = extra availability
    reason: str = ""


@dataclass
class ResourceAvailability:
    """Weekly recurring availability for a resource, plus exceptions."""

    resource_id: str
    recurring_slots: list[TimeSlot] = field(default_factory=list)
    exceptions: list[DateException] = field(default_factory=list)


@dataclass
class TravelPlan:
    """A client's travel commitment with adherence level."""

    start_date: date
    end_date: date
    destination: str
    adherence: TravelAdherence

    # What's available at the destination
    has_gym_access: bool = False
    has_kitchen_access: bool = False
    remote_consultation_ok: bool = True
    available_equipment: list[str] = field(default_factory=list)


@dataclass
class ClientAvailability:
    """The client's overall availability profile."""

    client_id: str
    recurring_slots: list[TimeSlot] = field(default_factory=list)
    travel_plans: list[TravelPlan] = field(default_factory=list)
    home_location_id: str = "loc_home"

    # Sleep schedule (inviolable — nothing scheduled in this window)
    sleep_start: time = field(default_factory=lambda: time(22, 30))
    sleep_end: time = field(default_factory=lambda: time(6, 0))

    # Work hours (optional constraint)
    work_start: Optional[time] = field(default_factory=lambda: time(9, 0))
    work_end: Optional[time] = field(default_factory=lambda: time(17, 0))
    work_days: list[DayOfWeek] = field(
        default_factory=lambda: [
            DayOfWeek.MONDAY,
            DayOfWeek.TUESDAY,
            DayOfWeek.WEDNESDAY,
            DayOfWeek.THURSDAY,
            DayOfWeek.FRIDAY,
        ]
    )


# ═══════════════════════════════════════════════════════════
#  SCHEDULE OUTPUT
# ═══════════════════════════════════════════════════════════

# Color codes for the React UI, derived from activity type
ACTIVITY_COLOR_MAP: dict[ActivityType, str] = {
    ActivityType.FITNESS: "#4CAF50",
    ActivityType.FOOD_CONSUMPTION: "#FF9800",
    ActivityType.MEDICATION: "#2196F3",
    ActivityType.THERAPY: "#9C27B0",
    ActivityType.CONSULTATION: "#F44336",
}

BLOCK_TYPE_COLOR_MAP: dict[ScheduleBlockType, str] = {
    ScheduleBlockType.PREP: "#78909C",
    ScheduleBlockType.TRANSIT: "#607D8B",
    ScheduleBlockType.TRAVEL_DAY: "#00BCD4",
}


def _generate_block_id() -> str:
    """Generate a unique block ID."""
    return f"blk_{uuid.uuid4().hex[:8]}"


@dataclass
class ScheduleBlock:
    """
    A single time block in the calendar.

    Can be an activity, prep, transit, or travel-day marker.
    """

    block_type: ScheduleBlockType
    activity_id: Optional[str]
    activity_name: str
    activity_type: Optional[ActivityType]
    date: date
    start_time: time
    end_time: time
    facilitator_id: Optional[str] = None
    facilitator_name: str = ""
    location: str = ""
    is_remote: bool = False
    is_backup: bool = False
    original_activity_id: Optional[str] = None
    metrics_to_collect: list[str] = field(default_factory=list)
    notes: str = ""
    block_id: str = field(default_factory=_generate_block_id)

    @property
    def color_code(self) -> str:
        """Derive color from activity type or block type."""
        if self.block_type == ScheduleBlockType.ACTIVITY and self.activity_type:
            return ACTIVITY_COLOR_MAP.get(self.activity_type, "#9E9E9E")
        return BLOCK_TYPE_COLOR_MAP.get(self.block_type, "#9E9E9E")

    @property
    def duration_minutes(self) -> int:
        """Calculate duration in minutes from start and end times."""
        start_total = self.start_time.hour * 60 + self.start_time.minute
        end_total = self.end_time.hour * 60 + self.end_time.minute
        return end_total - start_total


@dataclass
class DaySchedule:
    """All blocks for a single day."""

    date: date
    day_of_week: DayOfWeek
    blocks: list[ScheduleBlock] = field(default_factory=list)
    is_travel_day: bool = False
    travel_destination: Optional[str] = None
    travel_adherence: Optional[TravelAdherence] = None


@dataclass
class UnscheduledActivity:
    """An activity that could not be placed in the schedule."""

    activity_id: str
    activity_name: str
    activity_type: ActivityType
    target_date: date
    reason: str
    adjustment: str  # From Activity.skip_adjustment


@dataclass
class FullSchedule:
    """
    The complete 3-month schedule.

    Contains day-by-day schedules and a list of activities
    that could not be scheduled.
    """

    start_date: date
    end_date: date
    days: list[DaySchedule] = field(default_factory=list)
    unscheduled: list[UnscheduledActivity] = field(default_factory=list)

    @property
    def total_days(self) -> int:
        """Total number of days in the schedule."""
        return len(self.days)

    @property
    def total_scheduled(self) -> int:
        """Total number of scheduled activity blocks (not prep/transit)."""
        return sum(
            1
            for day in self.days
            for block in day.blocks
            if block.block_type == ScheduleBlockType.ACTIVITY
        )

    @property
    def total_unscheduled(self) -> int:
        """Total number of activities that could not be scheduled."""
        return len(self.unscheduled)
