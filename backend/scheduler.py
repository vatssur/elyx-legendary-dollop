# AGENT-MODIFIED: Core scheduling engine for Health Resource Allocator
"""
Priority-driven scheduling engine that allocates health activities
into a 3-month calendar, respecting resource availability, client
travel plans, and activity constraints.

Algorithm Phases:
  1. Anchor meals at their configured time windows
  2. Anchor medications relative to their linked meals
  3. Schedule all remaining activities by priority
  4. Week-based fallback — try unscheduled on other weekdays, then backups
  5. Cross-day fallback over the full 3-month window

Key features:
  - Back-to-back same-location optimization
  - Travel adherence (STRICT / FLEXIBLE / BREAK)
  - Transit and prep block insertion
  - Medication never skipped, even in BREAK mode
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Optional

from models import (
    LOCATION_ANYWHERE,
    LOCATION_HOME,
    LOCATION_GYM,
    SUBTYPE_BREAKFAST,
    SUBTYPE_LUNCH,
    SUBTYPE_DINNER,
    Activity,
    ActivityType,
    ClientAvailability,
    DayOfWeek,
    DaySchedule,
    DateException,
    FrequencyPeriod,
    FullSchedule,
    MealRelation,
    MealType,
    Resource,
    ResourceAvailability,
    ResourceType,
    ScheduleBlock,
    ScheduleBlockType,
    TimeSlot,
    TravelAdherence,
    TravelPlan,
    UnscheduledActivity,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════

SLOT_GRANULARITY_MINUTES = 5  # Schedule in 5-min increments
DAY_START_HOUR = 0
DAY_END_HOUR = 24

# Priority threshold for FLEXIBLE travel mode
# Activities with priority <= this value are considered "high priority"
FLEXIBLE_PRIORITY_THRESHOLD = 20

# Maximum number of activities with the same subtype allowed per day.
# 2 means two strength activities can share a day (harder constraint = 1).
MAX_SAME_SUBTYPE_PER_DAY = 2

# Activity types that should NOT be scheduled during the client's work hours
# when they are at a non-home location (home-based activities like stretching,
# eye exercises, meditation are OK since they don't need transit).
# Meals and medications are always exempt.
WORK_HOURS_BLOCKED_TYPES = frozenset({
    ActivityType.FITNESS,
    ActivityType.THERAPY,
    ActivityType.CONSULTATION,
})

# Map Python weekday (0=Monday) to our DayOfWeek enum
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
#  HELPER: TIME ARITHMETIC
# ═══════════════════════════════════════════════════════════


def _time_to_minutes(t: time) -> int:
    """Convert a time object to minutes since midnight."""
    return t.hour * 60 + t.minute


def _minutes_to_time(minutes: int) -> time:
    """
    Convert minutes since midnight to a time object.

    Args:
        minutes: Minutes since midnight (0-1439).

    Returns:
        Corresponding time object.
    """
    minutes = max(0, min(1439, minutes))
    return time(minutes // 60, minutes % 60)


def _add_minutes(t: time, minutes: int) -> time:
    """
    Add minutes to a time, clamping at 23:59.

    Args:
        t: Base time.
        minutes: Minutes to add (can be negative).

    Returns:
        Resulting time, clamped to valid range.
    """
    total = _time_to_minutes(t) + minutes
    return _minutes_to_time(total)


# ═══════════════════════════════════════════════════════════
#  HELPER: AVAILABILITY CHECKS
# ═══════════════════════════════════════════════════════════


@dataclass
class SchedulerContext:
    """
    Holds all data needed by the scheduler during a run.

    Avoids passing many arguments through every function.
    """

    activities: list[Activity]
    resources: dict[str, Resource]  # Keyed by resource ID
    resource_availability: dict[str, ResourceAvailability]  # Keyed by resource ID
    client: ClientAvailability
    start_date: date
    end_date: date

    # Activity lookup by ID
    activity_map: dict[str, Activity] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.activity_map is None:
            self.activity_map = {a.id: a for a in self.activities}


def _get_day_of_week(d: date) -> DayOfWeek:
    """Get the DayOfWeek enum for a date."""
    return PYTHON_DOW_TO_ENUM[d.weekday()]


def _get_travel_plan(
    client: ClientAvailability,
    target_date: date,
) -> Optional[TravelPlan]:
    """
    Check if the client is traveling on a given date.

    Args:
        client: The client's availability.
        target_date: Date to check.

    Returns:
        TravelPlan if traveling, None otherwise.
    """
    for tp in client.travel_plans:
        if tp.start_date <= target_date <= tp.end_date:
            return tp
    return None


def _is_resource_available(
    resource_id: str,
    target_date: date,
    start_time: time,
    end_time: time,
    ctx: SchedulerContext,
) -> bool:
    """
    Check if a resource is available at a specific date and time.

    Checks both recurring weekly schedule and date exceptions.

    Args:
        resource_id: The resource to check.
        target_date: Date to check.
        start_time: Start of the desired slot.
        end_time: End of the desired slot.
        ctx: Scheduler context with availability data.

    Returns:
        True if the resource is available for the full slot.
    """
    avail = ctx.resource_availability.get(resource_id)
    if avail is None:
        # No availability data means always available (e.g., SELF)
        return True

    # Check exceptions first
    for exc in avail.exceptions:
        if exc.start_date <= target_date <= exc.end_date and not exc.available:
            return False

    # Check recurring slots
    dow = _get_day_of_week(target_date)
    slot_start = _time_to_minutes(start_time)
    slot_end = _time_to_minutes(end_time)

    for slot in avail.recurring_slots:
        if slot.day_of_week != dow:
            continue
        avail_start = _time_to_minutes(slot.start_time)
        avail_end = _time_to_minutes(slot.end_time)
        if avail_start <= slot_start and slot_end <= avail_end:
            return True

    return False


def _is_in_sleep_block(
    client: ClientAvailability,
    start_time: time,
    end_time: time,
) -> bool:
    """
    Check if a time slot falls within the client's sleep block.

    Args:
        client: Client availability with sleep schedule.
        start_time: Slot start.
        end_time: Slot end.

    Returns:
        True if the slot overlaps with sleep.
    """
    sleep_start = _time_to_minutes(client.sleep_start)
    sleep_end = _time_to_minutes(client.sleep_end)
    slot_start = _time_to_minutes(start_time)
    slot_end = _time_to_minutes(end_time)

    if sleep_start > sleep_end:
        # Sleep wraps midnight (e.g., 22:30 to 06:00)
        return slot_start >= sleep_start or slot_end <= sleep_end
    else:
        # Sleep doesn't wrap midnight
        return (
            (slot_start >= sleep_start and slot_start < sleep_end)
            or (slot_end > sleep_start and slot_end <= sleep_end)
        )


def _overlaps_existing(
    day_schedule: DaySchedule,
    start_time: time,
    end_time: time,
) -> bool:
    """
    Check if a time slot overlaps with any existing block in the day.

    Blocks with location "anywhere" (e.g., medications) are skipped because
    they don't occupy physical space — a pill can be taken concurrently with
    activities at other locations.

    Args:
        day_schedule: The day's current schedule.
        start_time: Proposed start time.
        end_time: Proposed end time.

    Returns:
        True if there is an overlap.
    """
    slot_start = _time_to_minutes(start_time)
    slot_end = _time_to_minutes(end_time)

    for block in day_schedule.blocks:
        if block.block_type == ScheduleBlockType.TRAVEL_DAY:
            continue
        if block.location == LOCATION_ANYWHERE:
            continue  # Medications don't occupy physical space

        blk_start = _time_to_minutes(block.start_time)
        blk_end = _time_to_minutes(block.end_time)

        # Overlap exists if slots are not disjoint
        if slot_start < blk_end and slot_end > blk_start:
            return True

    return False


def _respects_gap(
    day_schedule: DaySchedule,
    start_time: time,
    end_time: time,
    min_gap: int,
) -> bool:
    """
    Check that the proposed slot has enough gap from adjacent blocks.

    Args:
        day_schedule: The day's current schedule.
        start_time: Proposed start.
        end_time: Proposed end.
        min_gap: Minimum gap in minutes.

    Returns:
        True if the gap constraint is satisfied.
    """
    if min_gap <= 0:
        return True

    slot_start = _time_to_minutes(start_time)
    slot_end = _time_to_minutes(end_time)

    for block in day_schedule.blocks:
        if block.block_type == ScheduleBlockType.TRAVEL_DAY:
            continue

        blk_start = _time_to_minutes(block.start_time)
        blk_end = _time_to_minutes(block.end_time)

        # Check if proposed slot is too close to an existing block
        if slot_end <= blk_start:
            # Proposed slot is before the block
            if blk_start - slot_end < min_gap:
                return False
        elif slot_start >= blk_end:
            # Proposed slot is after the block
            if slot_start - blk_end < min_gap:
                return False

    return True


# ═══════════════════════════════════════════════════════════
#  HELPER: FIND THE PREVIOUS LOCATION
# ═══════════════════════════════════════════════════════════


def _get_last_location_before(
    day_schedule: DaySchedule,
    before_time: time,
    home_location: str,
) -> str:
    """
    Get the location of the last activity block before a given time.

    Used to determine if transit is needed.

    Args:
        day_schedule: The day's schedule.
        before_time: The reference time.
        home_location: The client's home location name.

    Returns:
        Location name of the last activity, or home if none.
    """
    last_location = home_location
    last_end = 0

    for block in day_schedule.blocks:
        if block.block_type in (ScheduleBlockType.TRAVEL_DAY, ScheduleBlockType.TRANSIT):
            continue
        blk_end = _time_to_minutes(block.end_time)
        if blk_end <= _time_to_minutes(before_time) and blk_end > last_end:
            last_end = blk_end
            last_location = block.location

    return last_location


# ═══════════════════════════════════════════════════════════
#  CORE: FIND AVAILABLE SLOT
# ═══════════════════════════════════════════════════════════


def _find_slot(
    activity: Activity,
    day_schedule: DaySchedule,
    target_date: date,
    ctx: SchedulerContext,
    is_remote: bool = False,
    scan_reverse: bool = False,
) -> Optional[int]:
    """
    Find an available slot for an activity on a given day.

    Scans from earliest_start to latest_start in SLOT_GRANULARITY
    increments (or reverse if scan_reverse=True), checking all constraints.

    Args:
        activity: The activity to schedule.
        day_schedule: The current day's schedule.
        target_date: The target date.
        ctx: Scheduler context.
        is_remote: Whether this is being scheduled as a remote activity.
        scan_reverse: If True, scan from latest_start backwards.

    Returns:
        Start time in minutes since midnight, or None.
    """
    # Determine the scan window
    earliest = _time_to_minutes(activity.earliest_start) if activity.earliest_start else _time_to_minutes(ctx.client.sleep_end)
    latest = _time_to_minutes(activity.latest_start) if activity.latest_start else (_time_to_minutes(ctx.client.sleep_start) - activity.duration_minutes)

    # On weekdays, push the scan start after work for non-home FITNESS/THERAPY/CONSULTATION
    # so these activities land in the after-work window rather than early morning.
    if (
        activity.activity_type in WORK_HOURS_BLOCKED_TYPES
        and activity.location_name != LOCATION_HOME
        and ctx.client.work_start is not None
        and ctx.client.work_end is not None
    ):
        dow = _get_day_of_week(target_date)
        if dow in ctx.client.work_days:
            work_e = _time_to_minutes(ctx.client.work_end)
            if earliest < work_e:
                earliest = work_e

    # Include transit time in total duration
    location = activity.location_name
    total_duration = activity.duration_minutes

    scan_range = range(latest, earliest - 1, -SLOT_GRANULARITY_MINUTES) if scan_reverse else range(earliest, latest + 1, SLOT_GRANULARITY_MINUTES)
    for scan_start in scan_range:
        candidate_start = _minutes_to_time(scan_start)

        # Calculate transit needs
        transit_needed = 0
        if not is_remote and location != LOCATION_HOME and activity.transit_minutes_from_home > 0:
            prev_location = _get_last_location_before(
                day_schedule, candidate_start, LOCATION_HOME
            )
            if prev_location != location:
                transit_needed = activity.transit_minutes_from_home
                if prev_location != LOCATION_HOME:
                    # Between two non-home locations: heuristic
                    transit_needed = int(activity.transit_minutes_from_home * 0.7)

        # Total time block needed (transit happens before the activity)
        actual_start = scan_start
        activity_start = scan_start + transit_needed
        activity_end = activity_start + total_duration

        if activity_end > _time_to_minutes(ctx.client.sleep_start):
            continue  # Would extend into sleep

        activity_start_time = _minutes_to_time(activity_start)
        activity_end_time = _minutes_to_time(activity_end)

        # Check sleep block
        if _is_in_sleep_block(ctx.client, candidate_start, activity_end_time):
            continue

        # ── Work-hours enforcement ────────────────────────────────
        # Physical activities (FITNESS, THERAPY, CONSULTATION) at
        # non-home locations must not be placed during work hours.
        # Home-based activities (eye exercises, stretching, meditation)
        # are short and don't need transit — they're OK during work.
        if (
            activity.activity_type in WORK_HOURS_BLOCKED_TYPES
            and activity.location_name != LOCATION_HOME
            and ctx.client.work_start is not None
            and ctx.client.work_end is not None
        ):
            dow = _get_day_of_week(target_date)
            if dow in ctx.client.work_days:
                work_s = _time_to_minutes(ctx.client.work_start)
                work_e = _time_to_minutes(ctx.client.work_end)
                # Reject if any part of the activity overlaps the work window
                if not (activity_end <= work_s or activity_start >= work_e):
                    continue

        # Check overlap with existing blocks (including transit portion)
        if transit_needed > 0:
            transit_start_time = _minutes_to_time(actual_start)
            transit_end_time = _minutes_to_time(actual_start + transit_needed)
            if _overlaps_existing(day_schedule, transit_start_time, transit_end_time):
                continue

        if _overlaps_existing(day_schedule, activity_start_time, activity_end_time):
            continue

        # Check gap constraints
        if not _respects_gap(day_schedule, activity_start_time, activity_end_time, activity.min_gap_after_minutes):
            continue

        # Check resource availability (skip for remote activities using remote-capable facilitator)
        if activity.facilitator_id and activity.facilitator_type != ResourceType.SELF:
            if not _is_resource_available(
                activity.facilitator_id,
                target_date,
                activity_start_time,
                activity_end_time,
                ctx,
            ):
                if not is_remote:
                    continue
                # For remote, check if facilitator is remote-capable
                resource = ctx.resources.get(activity.facilitator_id)
                if resource and not resource.remote_capable:
                    continue

        return scan_start

    return None


# ═══════════════════════════════════════════════════════════
#  CORE: PLACE ACTIVITY IN DAY
# ═══════════════════════════════════════════════════════════


def _place_activity(
    activity: Activity,
    day_schedule: DaySchedule,
    slot_start_minutes: int,
    ctx: SchedulerContext,
    is_remote: bool = False,
) -> bool:
    """
    Place an activity (with transit and prep blocks) into a day's schedule.

    Args:
        activity: The activity to place.
        day_schedule: The day to place it in.
        slot_start_minutes: The start time in minutes since midnight.
        ctx: Scheduler context.
        is_remote: Whether scheduled as remote.

    Returns:
        True if successfully placed.
    """
    location = "remote" if is_remote else activity.location_name
    facilitator_name = ""
    if activity.facilitator_id:
        resource = ctx.resources.get(activity.facilitator_id)
        if resource:
            facilitator_name = resource.name

    # Calculate transit
    transit_needed = 0
    if not is_remote and location != LOCATION_HOME and activity.transit_minutes_from_home > 0:
        prev_location = _get_last_location_before(
            day_schedule, _minutes_to_time(slot_start_minutes), LOCATION_HOME
        )
        if prev_location != location:
            transit_needed = activity.transit_minutes_from_home
            if prev_location != LOCATION_HOME:
                transit_needed = int(activity.transit_minutes_from_home * 0.7)

    # Insert transit block
    if transit_needed > 0:
        transit_start = _minutes_to_time(slot_start_minutes)
        transit_end = _minutes_to_time(slot_start_minutes + transit_needed)
        day_schedule.blocks.append(
            ScheduleBlock(
                block_type=ScheduleBlockType.TRANSIT,
                activity_id=activity.id,
                activity_name=f"Transit → {location}",
                activity_type=None,
                date=day_schedule.date,
                start_time=transit_start,
                end_time=transit_end,
                location=f"home → {location}",
                notes=f"{transit_needed} min transit",
            )
        )

    # Activity block
    activity_start = slot_start_minutes + transit_needed
    activity_end = activity_start + activity.duration_minutes

    day_schedule.blocks.append(
        ScheduleBlock(
            block_type=ScheduleBlockType.ACTIVITY,
            activity_id=activity.id,
            activity_name=activity.name,
            activity_type=activity.activity_type,
            date=day_schedule.date,
            start_time=_minutes_to_time(activity_start),
            end_time=_minutes_to_time(activity_end),
            facilitator_id=activity.facilitator_id,
            facilitator_name=facilitator_name,
            location=location,
            is_remote=is_remote,
            metrics_to_collect=activity.metrics,
            notes=activity.details,
        )
    )

    # Insert prep block (find a slot before the activity, any time that day)
    if activity.prep_duration_minutes > 0:
        prep_placed = _place_prep_block(
            activity, day_schedule, activity_start, ctx
        )
        if not prep_placed:
            logger.debug(
                "Could not place prep block for %s on %s",
                activity.name, day_schedule.date,
            )

    # Sort blocks by start time
    day_schedule.blocks.sort(key=lambda b: _time_to_minutes(b.start_time))

    return True


def _place_prep_block(
    activity: Activity,
    day_schedule: DaySchedule,
    activity_start_minutes: int,
    ctx: SchedulerContext,
) -> bool:
    """
    Find and place a prep block before the activity.

    Scans backwards from the activity start to find an open slot.

    Args:
        activity: The activity that needs prep.
        day_schedule: The day's schedule.
        activity_start_minutes: When the activity starts.
        ctx: Scheduler context.

    Returns:
        True if prep block was placed.
    """
    prep_duration = activity.prep_duration_minutes
    prep_buffer = activity.prep_buffer_minutes
    # Prep must end at least prep_buffer minutes before activity
    latest_prep_end = activity_start_minutes - prep_buffer

    # Scan backwards from latest possible prep end
    earliest_day_start = _time_to_minutes(ctx.client.sleep_end)

    for prep_end in range(latest_prep_end, earliest_day_start + prep_duration - 1, -SLOT_GRANULARITY_MINUTES):
        prep_start = prep_end - prep_duration
        if prep_start < earliest_day_start:
            continue

        prep_start_time = _minutes_to_time(prep_start)
        prep_end_time = _minutes_to_time(prep_end)

        if not _overlaps_existing(day_schedule, prep_start_time, prep_end_time):
            day_schedule.blocks.append(
                ScheduleBlock(
                    block_type=ScheduleBlockType.PREP,
                    activity_id=activity.id,
                    activity_name=f"Prep: {activity.prep_description}",
                    activity_type=None,
                    date=day_schedule.date,
                    start_time=prep_start_time,
                    end_time=prep_end_time,
                    location=activity.location_name,
                    notes=activity.prep_description,
                )
            )
            return True

    return False


# ═══════════════════════════════════════════════════════════
#  PHASE 1: ANCHOR MEALS
# ═══════════════════════════════════════════════════════════


def _schedule_meals(
    meal_activities: list[Activity],
    day_schedule: DaySchedule,
    target_date: date,
    ctx: SchedulerContext,
    travel_plan: Optional[TravelPlan],
) -> dict[MealType, int]:
    """
    Schedule meal activities at their configured time windows.

    Meals are the temporal anchors of the day — they're scheduled
    first, and medications are then positioned relative to them.

    Args:
        meal_activities: Activities of type FOOD_CONSUMPTION that are meal anchors.
        day_schedule: The day to schedule into.
        target_date: The target date.
        ctx: Scheduler context.
        travel_plan: Active travel plan, if any.

    Returns:
        Dict mapping MealType to the scheduled time (minutes since midnight).
    """
    meal_times: dict[MealType, int] = {}

    # Determine meal type from activity name
    for activity in meal_activities:
        meal_type = _infer_meal_type(activity)

        # During travel BREAK mode, only schedule meals needed as medication anchors
        if travel_plan and travel_plan.adherence == TravelAdherence.BREAK:
            # Still schedule meals because medications may depend on them
            pass

        slot_minutes = _find_slot(activity, day_schedule, target_date, ctx, scan_reverse=True)
        if slot_minutes is not None:
            _place_activity(activity, day_schedule, slot_minutes, ctx)
            # Record the meal's actual scheduled time (activity start, after transit)
            transit = 0
            if activity.location_name != LOCATION_HOME and activity.transit_minutes_from_home > 0:
                transit = activity.transit_minutes_from_home
            meal_times[meal_type] = slot_minutes + transit
        else:
            logger.warning(
                "Could not schedule meal %s on %s", activity.name, target_date
            )

    return meal_times


def _infer_meal_type(activity: Activity) -> MealType:
    """
    Infer the MealType from an activity's subtype.

    Uses the activity's subtype field instead of name matching
    to determine meal type, per scheduler philosophy (no name knowledge).

    Args:
        activity: A food consumption activity.

    Returns:
        The inferred MealType.
    """
    subtype = activity.subtype.lower()
    if subtype == SUBTYPE_BREAKFAST:
        return MealType.BREAKFAST
    elif subtype == SUBTYPE_LUNCH:
        return MealType.LUNCH
    elif subtype == SUBTYPE_DINNER:
        return MealType.DINNER
    return MealType.ANY


# ═══════════════════════════════════════════════════════════
#  PHASE 2: ANCHOR MEDICATIONS TO MEALS
# ═══════════════════════════════════════════════════════════


def _schedule_medications(
    med_activities: list[Activity],
    day_schedule: DaySchedule,
    target_date: date,
    meal_times: dict[MealType, int],
    ctx: SchedulerContext,
) -> None:
    """
    Schedule medication activities relative to their linked meals.

    Medications with meal_relation != NONE are placed at a fixed
    offset from their linked meal. Others are placed at their
    configured time window.

    Args:
        med_activities: Medication activities to schedule.
        day_schedule: The day to schedule into.
        target_date: The target date.
        meal_times: Scheduled meal times from Phase 1.
        ctx: Scheduler context.
    """
    for activity in med_activities:
        if activity.meal_relation == MealRelation.NONE:
            # No meal relation — schedule at configured time
            slot_minutes = _find_slot(activity, day_schedule, target_date, ctx)
            if slot_minutes is not None:
                _place_activity(activity, day_schedule, slot_minutes, ctx)
            else:
                logger.warning(
                    "CRITICAL: Could not schedule medication %s on %s",
                    activity.name, target_date,
                )
            continue

        # Find the linked meal's time
        meal_type = activity.meal_relation_type
        linked_meal_time: Optional[int] = None

        if meal_type == MealType.ANY:
            # Use the first available meal
            for mt in [MealType.BREAKFAST, MealType.LUNCH, MealType.DINNER]:
                if mt in meal_times:
                    linked_meal_time = meal_times[mt]
                    break
        else:
            linked_meal_time = meal_times.get(meal_type)

        if linked_meal_time is None:
            # Meal not scheduled — try to schedule medication independently
            logger.warning(
                "Linked meal %s not found for %s on %s, scheduling independently",
                meal_type.value, activity.name, target_date,
            )
            slot_minutes = _find_slot(activity, day_schedule, target_date, ctx)
            if slot_minutes is not None:
                _place_activity(activity, day_schedule, slot_minutes, ctx)
            continue

        # Calculate medication time relative to meal
        offset = activity.meal_relation_offset_minutes
        if activity.meal_relation == MealRelation.BEFORE_MEAL:
            med_time = linked_meal_time - offset
        elif activity.meal_relation == MealRelation.AFTER_MEAL:
            # Assume meal is ~30 min, so "after meal" = meal_start + 30 + offset
            med_time = linked_meal_time + 30 + offset
        else:  # WITH_MEAL
            # Place at meal start — intentionally overlaps with the meal block
            _place_activity(activity, day_schedule, linked_meal_time, ctx)
            continue

        med_time = max(0, min(1430, med_time))  # Clamp to valid range

        # Check if the slot is free
        med_start = _minutes_to_time(med_time)
        med_end = _minutes_to_time(med_time + activity.duration_minutes)

        if not _overlaps_existing(day_schedule, med_start, med_end):
            _place_activity(activity, day_schedule, med_time, ctx)
        else:
            # Try nearby times (±15 min)
            placed = False
            for delta in range(5, 20, 5):
                for sign in [1, -1]:
                    alt_time = med_time + (delta * sign)
                    alt_start = _minutes_to_time(alt_time)
                    alt_end = _minutes_to_time(alt_time + activity.duration_minutes)
                    if not _overlaps_existing(day_schedule, alt_start, alt_end):
                        _place_activity(activity, day_schedule, alt_time, ctx)
                        placed = True
                        break
                if placed:
                    break

            if not placed:
                logger.warning(
                    "CRITICAL: Could not schedule medication %s on %s",
                    activity.name, target_date,
                )


# ═══════════════════════════════════════════════════════════
#  PHASE 3: SCHEDULE REMAINING ACTIVITIES
# ═══════════════════════════════════════════════════════════


def _should_schedule_on_travel_day(
    activity: Activity,
    travel_plan: TravelPlan,
    ctx: SchedulerContext,
) -> tuple[bool, bool]:
    """
    Determine if an activity should be scheduled during travel.

    Returns (should_schedule, force_remote).

    Args:
        activity: The activity in question.
        travel_plan: Active travel plan.
        ctx: Scheduler context.

    Returns:
        Tuple of (should_schedule, force_remote).
    """
    adherence = travel_plan.adherence

    # Medications are NEVER skipped
    if activity.activity_type == ActivityType.MEDICATION:
        return True, False

    # BREAK mode: skip everything except medications
    if adherence == TravelAdherence.BREAK:
        return False, False

    # FLEXIBLE mode: only high priority + remote-capable
    if adherence == TravelAdherence.FLEXIBLE:
        is_high_priority = activity.priority <= FLEXIBLE_PRIORITY_THRESHOLD
        if activity.remote_capable:
            return True, True
        if is_high_priority and activity.remote_capable:
            return True, True
        if is_high_priority:
            # Try to find a remote backup
            return False, False  # Will try backups later
        return False, False

    # STRICT mode: try to schedule everything
    if activity.remote_capable:
        return True, True

    # Check if the activity can be done at the destination
    if activity.location_name == LOCATION_GYM and travel_plan.has_gym_access:
        return True, False
    if activity.location_name == LOCATION_HOME and travel_plan.has_kitchen_access:
        return True, False

    # Not remote-capable and location not available — will try backups
    return False, False


def _try_schedule_activity(
    activity: Activity,
    day_schedule: DaySchedule,
    target_date: date,
    ctx: SchedulerContext,
    travel_plan: Optional[TravelPlan] = None,
) -> bool:
    """
    Try to schedule an activity.
    """
    # --- SUBTYPE CHECK ---
    # Allow up to MAX_SAME_SUBTYPE_PER_DAY activities of the same subtype per day.
    same_subtype_count = 0
    for block in day_schedule.blocks:
        if block.block_type == ScheduleBlockType.ACTIVITY and block.activity_id:
            scheduled_act = ctx.activity_map.get(block.activity_id)
            if scheduled_act and scheduled_act.subtype == activity.subtype:
                same_subtype_count += 1
    if same_subtype_count >= MAX_SAME_SUBTYPE_PER_DAY:
        return False

    if travel_plan:
        should_schedule, force_remote = _should_schedule_on_travel_day(
            activity, travel_plan, ctx
        )

        if not should_schedule:
            return False

        if force_remote:
            slot_minutes = _find_slot(activity, day_schedule, target_date, ctx, is_remote=True)
            if slot_minutes is not None:
                _place_activity(
                    activity, day_schedule, slot_minutes, ctx, is_remote=True,
                )
                return True
            return False

    # Normal scheduling (or STRICT travel where location is available)
    slot_minutes = _find_slot(activity, day_schedule, target_date, ctx)
    if slot_minutes is not None:
        _place_activity(activity, day_schedule, slot_minutes, ctx)
        return True

    # Backup fallback: try each backup activity in order
    for backup_id in activity.backup_activity_ids:
        backup_act = ctx.activity_map.get(backup_id)
        if backup_act is None:
            continue
        # Apply same subtype limit check to backup
        backup_subtype_count = 0
        for block in day_schedule.blocks:
            if block.block_type == ScheduleBlockType.ACTIVITY and block.activity_id:
                scheduled_act = ctx.activity_map.get(block.activity_id)
                if scheduled_act and scheduled_act.subtype == backup_act.subtype:
                    backup_subtype_count += 1
        if backup_subtype_count >= MAX_SAME_SUBTYPE_PER_DAY:
            continue
        backup_slot = _find_slot(backup_act, day_schedule, target_date, ctx)
        if backup_slot is not None:
            _place_activity(backup_act, day_schedule, backup_slot, ctx)
            return True

    return False


# ═══════════════════════════════════════════════════════════
#  SAME-LOCATION OPTIMIZATION
# ═══════════════════════════════════════════════════════════


def _try_week_fallback(
    unscheduled: list[UnscheduledActivity],
    schedule: FullSchedule,
    ctx: SchedulerContext,
    week_start: date,
) -> None:
    """
    Phase 4: Week-based fallback for unscheduled activities.

    For each activity that couldn't fit on its target day, try:
      1. Schedule the activity on another day within the same 7-day window
      2. If that fails, schedule a backup activity on another day in the window
    """
    start_of_week = week_start
    end_of_week = start_of_week + timedelta(days=6)

    scheduled_subtypes: dict[int, set[str]] = {}
    day_index: dict[date, DaySchedule] = {}
    for day_sch in schedule.days:
        day_index[day_sch.date] = day_sch
        if start_of_week <= day_sch.date <= end_of_week:
            offset = (day_sch.date - start_of_week).days
            subtypes: set[str] = set()
            for block in day_sch.blocks:
                if block.block_type == ScheduleBlockType.ACTIVITY and block.activity_id:
                    act = ctx.activity_map.get(block.activity_id)
                    if act and act.subtype:
                        subtypes.add(act.subtype)
            scheduled_subtypes[offset] = subtypes

    remaining: list[UnscheduledActivity] = []
    for entry in unscheduled:
        if entry.target_date < start_of_week or entry.target_date > end_of_week:
            remaining.append(entry)
            continue

        activity = ctx.activity_map.get(entry.activity_id)
        if activity is None:
            remaining.append(entry)
            continue

        if activity.activity_type in (ActivityType.FOOD_CONSUMPTION, ActivityType.MEDICATION):
            remaining.append(entry)
            continue

        placed = False
        target_offset = (entry.target_date - start_of_week).days

        # Try the activity itself on other days in the week
        for day_offset in range(7):
            if day_offset == target_offset:
                continue
            day = start_of_week + timedelta(days=day_offset)
            day_entry = day_index.get(day)
            if day_entry is None or day_entry.travel_adherence == TravelAdherence.BREAK:
                continue

            if activity.subtype and activity.subtype in scheduled_subtypes.get(day_offset, set()):
                continue

            slot = _find_slot(activity, day_entry, day, ctx)
            if slot is not None:
                _place_activity(activity, day_entry, slot, ctx)
                if activity.subtype:
                    scheduled_subtypes.setdefault(day_offset, set()).add(activity.subtype)
                placed = True
                logger.info(
                    "Week fallback: '%s' moved from %s to %s",
                    activity.name, entry.target_date, day,
                )
                break

        # If activity didn't fit, try its backups on other days in the week
        if not placed:
            for backup_id in activity.backup_activity_ids:
                backup_act = ctx.activity_map.get(backup_id)
                if backup_act is None:
                    continue
                for day_offset in range(7):
                    if day_offset == target_offset:
                        continue
                    day = start_of_week + timedelta(days=day_offset)
                    day_entry = day_index.get(day)
                    if day_entry is None or day_entry.travel_adherence == TravelAdherence.BREAK:
                        continue

                    if backup_act.subtype and backup_act.subtype in scheduled_subtypes.get(day_offset, set()):
                        continue

                    slot = _find_slot(backup_act, day_entry, day, ctx)
                    if slot is not None:
                        _place_activity(backup_act, day_entry, slot, ctx)
                        if backup_act.subtype:
                            scheduled_subtypes.setdefault(day_offset, set()).add(backup_act.subtype)
                        placed = True
                        logger.info(
                            "Week fallback (backup): '%s' placed for '%s' on %s",
                            backup_act.name, activity.name, day,
                        )
                        break
                if placed:
                    break

        if not placed:
            remaining.append(entry)

    # Replace the full unscheduled list with what's left
    schedule.unscheduled = remaining


# ═══════════════════════════════════════════════════════════
#  MAIN: GENERATE FULL SCHEDULE
# ═══════════════════════════════════════════════════════════


def _compute_weekly_assignments(
    activities: list[Activity],
    client: ClientAvailability,
) -> dict[str, list[int]]:
    """
    Assign each weekly activity to specific weekdays based on load.

    For each activity instance, picks the least-loaded compatible day.
    Available time for a day = 1440 - sleep - work(if activity is non-home
    and weekday) - already scheduled duration.

    This naturally places non-home activities on weekends (more available
    time) and home activities across all days evenly.

    Args:
        activities: All activities to assign.
        client: Client availability (sleep/work times).

    Returns:
        Dict mapping activity_id -> sorted list of weekday indices (0=Mon).
    """
    sleep_minutes = 0.0
    if client.sleep_start and client.sleep_end:
        sleep_start = _time_to_minutes(client.sleep_start)
        sleep_end = _time_to_minutes(client.sleep_end)
        if sleep_start > sleep_end:
            sleep_minutes = 1440.0 - sleep_start + sleep_end
        else:
            sleep_minutes = float(sleep_end - sleep_start)

    work_minutes = 0.0
    if client.work_start and client.work_end:
        work_minutes = float(
            _time_to_minutes(client.work_end) - _time_to_minutes(client.work_start)
        )

    day_load: list[float] = [0.0] * 7
    day_subtypes: list[dict[str, int]] = [{} for _ in range(7)]
    day_type_counts: list[dict[ActivityType, int]] = [{} for _ in range(7)]
    assignments: dict[str, list[int]] = {}

    weekly_acts = sorted(
        [a for a in activities
         if a.frequency_period == FrequencyPeriod.WEEKLY and a.frequency_times < 7],
        key=lambda a: a.priority,
        reverse=True,
    )

    for act in weekly_acts:
        freq = act.frequency_times
        act_days: list[int] = []
        available_days = list(range(7))
        for _ in range(freq):
            # Filter out days already at the subtype limit for this activity
            days_pool = available_days
            if act.subtype:
                days_pool = [d for d in available_days
                             if day_subtypes[d].get(act.subtype, 0)
                             < MAX_SAME_SUBTYPE_PER_DAY]
                if not days_pool:
                    days_pool = available_days
            weights: list[float] = []
            for d in days_pool:
                avail = 1440.0 - sleep_minutes - day_load[d]
                if act.location_name not in ("home", LOCATION_ANYWHERE) and d < 5:
                    avail -= work_minutes
                # Diversity bonus: penalize days already heavy on this activity type
                same_type_count = day_type_counts[d].get(act.activity_type, 0)
                avail /= (1.0 + same_type_count)
                weights.append(max(avail, 1.0))
            chosen = random.choices(days_pool, weights=weights, k=1)[0]
            act_days.append(chosen)
            day_load[chosen] += float(act.duration_minutes)
            if act.subtype:
                day_subtypes[chosen][act.subtype] = day_subtypes[chosen].get(act.subtype, 0) + 1
            day_type_counts[chosen][act.activity_type] = day_type_counts[chosen].get(act.activity_type, 0) + 1
            available_days.remove(chosen)
        assignments[act.id] = sorted(act_days)

    return assignments


def _get_activities_for_day(
    activities: list[Activity],
    target_date: date,
    schedule_start: date,
    weekly_assignments: dict[str, list[int]] | None = None,
) -> list[Activity]:
    """
    Determine which activities need to be scheduled on a given day.

    Applies frequency logic: daily activities every day, weekly
    activities spread across the week (using pre-computed load-aware
    assignments), monthly activities once.

    Args:
        activities: All activities in the action plan.
        target_date: The target date.
        schedule_start: Start of the schedule window.
        weekly_assignments: Pre-computed day assignments for weekly activities.

    Returns:
        List of activities that should be scheduled on this day.
    """
    dow = _get_day_of_week(target_date)
    day_of_week_idx = target_date.weekday()  # 0=Monday
    day_in_month = target_date.day

    result: list[Activity] = []

    for activity in activities:
        # Check preferred days
        if activity.preferred_days and dow not in activity.preferred_days:
            continue

        if activity.frequency_period == FrequencyPeriod.DAILY:
            result.append(activity)
        elif activity.frequency_period == FrequencyPeriod.WEEKLY:
            freq = activity.frequency_times
            if freq >= 7:
                result.append(activity)
            else:
                days_for_freq: list[int] = []
                if weekly_assignments and activity.id in weekly_assignments:
                    days_for_freq = weekly_assignments[activity.id]
                if day_of_week_idx in days_for_freq:
                    result.append(activity)
        elif activity.frequency_period == FrequencyPeriod.MONTHLY:
            # Schedule on specific week(s) of the month
            freq = activity.frequency_times
            if freq == 1:
                # First week of month
                if day_in_month <= 7 and day_of_week_idx == 1:  # Tuesday
                    result.append(activity)
            elif freq == 2:
                # First and third week
                if day_in_month <= 7 and day_of_week_idx == 1:
                    result.append(activity)
                elif 14 < day_in_month <= 21 and day_of_week_idx == 1:
                    result.append(activity)
            else:
                # Monthly activities with freq > 2: distribute evenly within month
                if weekly_assignments and activity.id in weekly_assignments:
                    days_for_freq = weekly_assignments[activity.id]
                else:
                    days_for_freq = [0, 2, 4, 1, 3]  # fallback
                if day_of_week_idx in days_for_freq:
                    result.append(activity)

    return result


def _cross_day_fallback(
    schedule: FullSchedule,
    ctx: SchedulerContext,
    start_date: date,
    end_date: date,
) -> int:
    """
    Phase 5: Cross-day fallback for unscheduled activities.

    Attempts to reschedule activities that couldn't fit on their target day
    onto any other day in the schedule window that doesn't already have
    an activity with the same subtype. Each attempted day is tried in
    chronological order; the first compatible slot wins.

    Returns:
        Number of activities successfully recovered.
    """
    scheduled_subtypes: dict[int, set[str]] = {}
    for day_sch in schedule.days:
        offset = (day_sch.date - start_date).days
        subtypes: set[str] = set()
        for block in day_sch.blocks:
            if block.block_type == ScheduleBlockType.ACTIVITY and block.activity_id:
                act = ctx.activity_map.get(block.activity_id)
                if act and act.subtype:
                    subtypes.add(act.subtype)
        scheduled_subtypes[offset] = subtypes

    recovered = 0
    remaining: list[UnscheduledActivity] = []

    for entry in schedule.unscheduled:
        activity = ctx.activity_map.get(entry.activity_id)
        if activity is None:
            remaining.append(entry)
            continue

        if activity.activity_type in (ActivityType.FOOD_CONSUMPTION, ActivityType.MEDICATION):
            remaining.append(entry)
            continue

        target_offset = (entry.target_date - start_date).days

        placed = False
        for day_sch in schedule.days:
            day_offset = (day_sch.date - start_date).days

            if day_offset == target_offset:
                continue

            if activity.subtype and activity.subtype in scheduled_subtypes.get(day_offset, set()):
                continue

            if day_sch.travel_adherence == TravelAdherence.BREAK:
                continue

            slot = _find_slot(activity, day_sch, day_sch.date, ctx)
            if slot is not None:
                _place_activity(activity, day_sch, slot, ctx)

                if activity.subtype:
                    scheduled_subtypes.setdefault(day_offset, set()).add(activity.subtype)

                recovered += 1
                placed = True
                logger.info(
                    "Cross-day fallback: '%s' moved from %s to %s",
                    activity.name, entry.target_date, day_sch.date,
                )
                break

        if not placed:
            remaining.append(entry)

    schedule.unscheduled = remaining
    return recovered


def generate_schedule(
    activities: list[Activity],
    resources: list[Resource],
    resource_availability: list[ResourceAvailability],
    client: ClientAvailability,
    start_date: date,
    end_date: date,
    plan_ids: set[str] | None = None,
) -> FullSchedule:
    """
    Generate a complete schedule for the given date range.

    This is the main entry point for the scheduling engine.

    Args:
        activities: All activities (action plan + backup pool), sorted by priority.
        resources: All resources.
        resource_availability: Availability data for each resource.
        client: Client availability and travel plans.
        start_date: First day of the schedule.
        end_date: Last day of the schedule (inclusive).
        plan_ids: Set of activity IDs that form the action plan.
                  If None, all activities are scheduled.

    Returns:
        A FullSchedule containing day-by-day schedules and unscheduled items.
    """
    ctx = SchedulerContext(
        activities=activities,
        resources={r.id: r for r in resources},
        resource_availability={a.resource_id: a for a in resource_availability},
        client=client,
        start_date=start_date,
        end_date=end_date,
    )

    # Only schedule action plan activities.
    # The full activity pool remains in ctx.activity_map for backup resolution.
    if plan_ids is None:
        plan = activities[:]
    else:
        plan = [a for a in activities if a.id in plan_ids]

    schedule = FullSchedule(start_date=start_date, end_date=end_date)

    # Pre-compute load-aware weekly assignments for action plan only
    weekly_assignments = _compute_weekly_assignments(plan, client)

    # Categorize activities
    schedulable = plan

    meal_activities = [
        a for a in schedulable
        if a.activity_type == ActivityType.FOOD_CONSUMPTION
        and _infer_meal_type(a) != MealType.ANY
    ]
    med_activities = [
        a for a in schedulable
        if a.activity_type == ActivityType.MEDICATION
    ]
    other_activities = [
        a for a in schedulable
        if a not in meal_activities and a not in med_activities
    ]

    # Sort others: most constrained first (longer, larger gap, more transit),
    # then by priority as tiebreaker. This ensures hard-to-fit activities
    # like HIIT (long + 60-min gap + transit) get placed before flexible
    # ones like Brisk Walk (short + 5-min gap).
    other_activities.sort(key=lambda a: (
        -(a.duration_minutes + a.min_gap_after_minutes + a.transit_minutes_from_home),
        a.priority,
    ))

    # Track skip statistics for monitoring
    skip_stats: dict[str, int] = {}
    skip_by_type: dict[str, int] = {}

    current_date = start_date
    while current_date <= end_date:
        dow = _get_day_of_week(current_date)
        travel_plan = _get_travel_plan(client, current_date)

        day_schedule = DaySchedule(
            date=current_date,
            day_of_week=dow,
            is_travel_day=travel_plan is not None,
            travel_destination=travel_plan.destination if travel_plan else None,
            travel_adherence=travel_plan.adherence if travel_plan else None,
        )

        # Add travel day marker
        if travel_plan:
            day_schedule.blocks.append(
                ScheduleBlock(
                    block_type=ScheduleBlockType.TRAVEL_DAY,
                    activity_id=None,
                    activity_name=f"✈️ {travel_plan.destination} ({travel_plan.adherence.value})",
                    activity_type=None,
                    date=current_date,
                    start_time=time(0, 0),
                    end_time=time(23, 59),
                    location=travel_plan.destination,
                    notes=f"Travel adherence: {travel_plan.adherence.value}",
                )
            )

        # Get today's activities
        todays_meals = [a for a in meal_activities if a in _get_activities_for_day(meal_activities, current_date, start_date, weekly_assignments)]
        todays_meds = [a for a in med_activities if a in _get_activities_for_day(med_activities, current_date, start_date, weekly_assignments)]
        todays_other = [a for a in other_activities if a in _get_activities_for_day(other_activities, current_date, start_date, weekly_assignments)]

        # PHASE 1: Anchor meals
        # During BREAK travel, still schedule meals for medication anchoring
        meal_times = _schedule_meals(
            todays_meals, day_schedule, current_date, ctx, travel_plan
        )

        # PHASE 2: Anchor medications (NEVER skip)
        _schedule_medications(
            todays_meds, day_schedule, current_date, meal_times, ctx
        )

        # PHASE 3: Schedule remaining by priority
        if travel_plan and travel_plan.adherence == TravelAdherence.BREAK:
            # BREAK mode: skip everything except already-scheduled meals & meds
            for activity in todays_other:
                reason = f"Travel BREAK mode ({travel_plan.destination})"
                schedule.unscheduled.append(
                    UnscheduledActivity(
                        activity_id=activity.id,
                        activity_name=activity.name,
                        activity_type=activity.activity_type,
                        target_date=current_date,
                        reason=reason,
                        adjustment=activity.skip_adjustment,
                    )
                )
                skip_stats[reason] = skip_stats.get(reason, 0) + 1
                skip_by_type[activity.activity_type.value] = skip_by_type.get(activity.activity_type.value, 0) + 1
        else:
            for activity in todays_other:
                success = _try_schedule_activity(
                    activity, day_schedule, current_date, ctx, travel_plan
                )
                if not success:
                    reason = "No available slot found"
                    subtype_collision = False
                    for block in day_schedule.blocks:
                        if block.block_type == ScheduleBlockType.ACTIVITY and block.activity_id:
                            scheduled_act = ctx.activity_map.get(block.activity_id)
                            if scheduled_act and scheduled_act.subtype == activity.subtype:
                                subtype_collision = True
                                break
                    if subtype_collision:
                        reason = f"Subtype collision (already have '{activity.subtype}' today)"
                    if travel_plan:
                        reason = f"Travel to {travel_plan.destination} ({travel_plan.adherence.value}) — no remote backup available"
                    schedule.unscheduled.append(
                        UnscheduledActivity(
                            activity_id=activity.id,
                            activity_name=activity.name,
                            activity_type=activity.activity_type,
                            target_date=current_date,
                            reason=reason,
                            adjustment=activity.skip_adjustment,
                        )
                    )
                    skip_stats[reason] = skip_stats.get(reason, 0) + 1
                    skip_by_type[activity.activity_type.value] = skip_by_type.get(activity.activity_type.value, 0) + 1

        # PHASE 4: Week-based fallback — try unscheduled activities on other
        # days in the same 7-day window (and their backups), before giving up.
        if schedule.unscheduled:
            week_unscheduled = [
                u for u in schedule.unscheduled
                if abs((u.target_date - current_date).days) <= 3
            ]
            if week_unscheduled:
                _try_week_fallback(week_unscheduled, schedule, ctx, current_date)

        schedule.days.append(day_schedule)
        current_date += timedelta(days=1)

    # PHASE 4: Week-based fallback — for each week, try to re-place unscheduled
    # activities on other days in that week (then their backups).
    weeks = (end_date - start_date).days // 7 + 1
    for w in range(weeks):
        week_start = start_date + timedelta(days=w * 7)
        week_end = min(week_start + timedelta(days=6), end_date)
        week_unscheduled = [
            u for u in schedule.unscheduled
            if week_start <= u.target_date <= week_end
        ]
        if week_unscheduled:
            _try_week_fallback(week_unscheduled, schedule, ctx, week_start)

    # PHASE 5: Cross-day fallback — try to place skipped activities on other days
    # that don't already have their subtype.
    recovered = _cross_day_fallback(schedule, ctx, start_date, end_date)
    if recovered:
        logger.info(
            "PHASE 5: Cross-day fallback recovered %d activities", recovered
        )

    # Log skip statistics for monitoring (helps identify if templates need adjustment)
    if skip_stats:
        total_skipped = sum(skip_stats.values())
        logger.warning(
            "SCHEDULE SUMMARY: %d activities skipped out of %d activity-days (%.1f%% skip rate)",
            total_skipped,
            len(schedule.days) * len([a for a in activities if a.activity_type not in (ActivityType.FOOD_CONSUMPTION, ActivityType.MEDICATION)]),
            total_skipped / max(1, len(schedule.days) * len([a for a in activities if a.activity_type not in (ActivityType.FOOD_CONSUMPTION, ActivityType.MEDICATION)])) * 100,
        )
        for reason, count in sorted(skip_stats.items(), key=lambda x: -x[1]):
            logger.warning("  Skip reason '%s': %d", reason, count)
        for atype, count in sorted(skip_by_type.items(), key=lambda x: -x[1]):
            logger.warning("  By type '%s': %d", atype, count)
    else:
        logger.info("SCHEDULE SUMMARY: No activities skipped")

    return schedule
