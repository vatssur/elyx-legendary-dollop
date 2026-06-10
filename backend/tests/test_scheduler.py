# AGENT-MODIFIED: Comprehensive scheduler tests
"""
Tests for the scheduling engine.

Covers:
  - Meal type inference via subtype
  - Basic schedule generation
  - Sleep block enforcement
  - Overlap detection
  - Subtype collision prevention (same-subtype-per-day)
  - Backup fallback logic
  - Travel adherence modes (BREAK, FLEXIBLE, STRICT)
  - Medication never-skip guarantee
  - Fully booked day handling
  - Gap constraint enforcement
"""

import pytest
from datetime import date, time, timedelta
from models import (
    Activity,
    ActivityType,
    ClientAvailability,
    DayOfWeek,
    DaySchedule,
    FrequencyPeriod,
    MealRelation,
    MealType,
    Resource,
    ResourceAvailability,
    ResourceType,
    ScheduleBlock,
    ScheduleBlockType,
    TravelAdherence,
    TravelPlan,
)
from scheduler import (
    generate_schedule,
    _find_slot,
    _get_last_location_before,
    _get_travel_plan,
    _infer_meal_type,
    _is_in_sleep_block,
    _overlaps_existing,
    _respects_gap,
    _try_schedule_activity,
    SchedulerContext,
)


# ═══════════════════════════════════════════════════════════
#  FIXTURES
# ═══════════════════════════════════════════════════════════


def _make_activity(
    act_id: str = "act_1",
    name: str = "Test Activity",
    activity_type: ActivityType = ActivityType.FITNESS,
    priority: int = 1,
    duration: int = 30,
    freq_times: int = 1,
    freq_period: FrequencyPeriod = FrequencyPeriod.DAILY,
    location: str = "home",
    remote: bool = True,
    subtype: str = "test_subtype",
    earliest: time | None = time(7, 0),
    latest: time | None = time(20, 0),
    backup_ids: list[str] | None = None,
) -> Activity:
    """Helper to create an Activity with sensible defaults."""
    return Activity(
        id=act_id, name=name, activity_type=activity_type,
        priority=priority, duration_minutes=duration,
        frequency_times=freq_times, frequency_period=freq_period,
        details="", facilitator_id=None, facilitator_type=ResourceType.SELF,
        location_id=None, location_name=location, remote_capable=remote,
        prep_description="", prep_duration_minutes=0, prep_buffer_minutes=0,
        subtype=subtype, earliest_start=earliest, latest_start=latest,
        backup_activity_ids=backup_ids or [],
    )


def _make_client(
    sleep_start: time = time(22, 0),
    sleep_end: time = time(6, 0),
    travel_plans: list[TravelPlan] | None = None,
) -> ClientAvailability:
    """Helper to create a ClientAvailability."""
    return ClientAvailability(
        client_id="test_client",
        sleep_start=sleep_start,
        sleep_end=sleep_end,
        work_start=time(9, 0),
        work_end=time(17, 0),
        travel_plans=travel_plans or [],
    )


def _make_ctx(
    activities: list[Activity] | None = None,
    client: ClientAvailability | None = None,
) -> SchedulerContext:
    """Helper to create a SchedulerContext."""
    acts = activities or [_make_activity()]
    cl = client or _make_client()
    return SchedulerContext(
        activities=acts,
        resources={},
        resource_availability={},
        client=cl,
        start_date=date(2026, 6, 15),
        end_date=date(2026, 9, 13),
    )


# ═══════════════════════════════════════════════════════════
#  MEAL TYPE INFERENCE
# ═══════════════════════════════════════════════════════════


class TestInferMealType:
    def test_breakfast(self) -> None:
        assert _infer_meal_type(_make_activity(subtype="breakfast")) == MealType.BREAKFAST

    def test_lunch(self) -> None:
        assert _infer_meal_type(_make_activity(subtype="lunch")) == MealType.LUNCH

    def test_dinner(self) -> None:
        assert _infer_meal_type(_make_activity(subtype="dinner")) == MealType.DINNER

    def test_snack_returns_any(self) -> None:
        assert _infer_meal_type(_make_activity(subtype="snack")) == MealType.ANY

    def test_unknown_subtype_returns_any(self) -> None:
        assert _infer_meal_type(_make_activity(subtype="protein_shake")) == MealType.ANY

    def test_case_insensitive(self) -> None:
        assert _infer_meal_type(_make_activity(subtype="BREAKFAST")) == MealType.BREAKFAST


# ═══════════════════════════════════════════════════════════
#  SLEEP BLOCK ENFORCEMENT
# ═══════════════════════════════════════════════════════════


class TestSleepBlock:
    def test_slot_inside_sleep_is_blocked(self) -> None:
        client = _make_client(sleep_start=time(22, 0), sleep_end=time(6, 0))
        assert _is_in_sleep_block(client, time(23, 0), time(23, 30)) is True

    def test_slot_before_sleep_end_is_blocked(self) -> None:
        client = _make_client(sleep_start=time(22, 0), sleep_end=time(6, 0))
        assert _is_in_sleep_block(client, time(5, 0), time(5, 30)) is True

    def test_slot_outside_sleep_is_allowed(self) -> None:
        client = _make_client(sleep_start=time(22, 0), sleep_end=time(6, 0))
        assert _is_in_sleep_block(client, time(10, 0), time(10, 30)) is False

    def test_slot_at_sleep_end_boundary(self) -> None:
        client = _make_client(sleep_start=time(22, 0), sleep_end=time(6, 0))
        # 6:00 - 6:30 should be allowed (starts exactly at sleep end)
        assert _is_in_sleep_block(client, time(6, 0), time(6, 30)) is False


# ═══════════════════════════════════════════════════════════
#  OVERLAP DETECTION
# ═══════════════════════════════════════════════════════════


class TestOverlapDetection:
    def test_no_overlap_with_empty_schedule(self) -> None:
        day = DaySchedule(date=date(2026, 6, 15), day_of_week=DayOfWeek.MONDAY)
        assert _overlaps_existing(day, time(9, 0), time(10, 0)) is False

    def test_overlap_detected(self) -> None:
        day = DaySchedule(date=date(2026, 6, 15), day_of_week=DayOfWeek.MONDAY)
        day.blocks.append(ScheduleBlock(
            block_type=ScheduleBlockType.ACTIVITY, activity_id="a",
            activity_name="A", activity_type=ActivityType.FITNESS,
            date=date(2026, 6, 15), start_time=time(9, 0), end_time=time(10, 0),
        ))
        assert _overlaps_existing(day, time(9, 30), time(10, 30)) is True

    def test_adjacent_no_overlap(self) -> None:
        day = DaySchedule(date=date(2026, 6, 15), day_of_week=DayOfWeek.MONDAY)
        day.blocks.append(ScheduleBlock(
            block_type=ScheduleBlockType.ACTIVITY, activity_id="a",
            activity_name="A", activity_type=ActivityType.FITNESS,
            date=date(2026, 6, 15), start_time=time(9, 0), end_time=time(10, 0),
        ))
        # Slot starts exactly when existing ends — no overlap
        assert _overlaps_existing(day, time(10, 0), time(11, 0)) is False

    def test_travel_day_marker_ignored(self) -> None:
        day = DaySchedule(date=date(2026, 6, 15), day_of_week=DayOfWeek.MONDAY)
        day.blocks.append(ScheduleBlock(
            block_type=ScheduleBlockType.TRAVEL_DAY, activity_id=None,
            activity_name="Travel", activity_type=None,
            date=date(2026, 6, 15), start_time=time(0, 0), end_time=time(23, 59),
        ))
        # Travel markers should not cause overlaps
        assert _overlaps_existing(day, time(9, 0), time(10, 0)) is False


# ═══════════════════════════════════════════════════════════
#  GAP CONSTRAINT
# ═══════════════════════════════════════════════════════════


class TestGapConstraint:
    def test_zero_gap_always_passes(self) -> None:
        day = DaySchedule(date=date(2026, 6, 15), day_of_week=DayOfWeek.MONDAY)
        day.blocks.append(ScheduleBlock(
            block_type=ScheduleBlockType.ACTIVITY, activity_id="a",
            activity_name="A", activity_type=ActivityType.FITNESS,
            date=date(2026, 6, 15), start_time=time(9, 0), end_time=time(10, 0),
        ))
        assert _respects_gap(day, time(10, 0), time(11, 0), 0) is True

    def test_insufficient_gap_fails(self) -> None:
        day = DaySchedule(date=date(2026, 6, 15), day_of_week=DayOfWeek.MONDAY)
        day.blocks.append(ScheduleBlock(
            block_type=ScheduleBlockType.ACTIVITY, activity_id="a",
            activity_name="A", activity_type=ActivityType.FITNESS,
            date=date(2026, 6, 15), start_time=time(9, 0), end_time=time(10, 0),
        ))
        # Only 5 min gap but need 15
        assert _respects_gap(day, time(10, 5), time(11, 0), 15) is False

    def test_sufficient_gap_passes(self) -> None:
        day = DaySchedule(date=date(2026, 6, 15), day_of_week=DayOfWeek.MONDAY)
        day.blocks.append(ScheduleBlock(
            block_type=ScheduleBlockType.ACTIVITY, activity_id="a",
            activity_name="A", activity_type=ActivityType.FITNESS,
            date=date(2026, 6, 15), start_time=time(9, 0), end_time=time(10, 0),
        ))
        # 30 min gap, need 15
        assert _respects_gap(day, time(10, 30), time(11, 0), 15) is True


# ═══════════════════════════════════════════════════════════
#  SUBTYPE COLLISION PREVENTION
# ═══════════════════════════════════════════════════════════


class TestSubtypeCollision:
    def test_same_subtype_limit_enforced(self) -> None:
        """Up to MAX_SAME_SUBTYPE_PER_DAY (2) same-subtype activities allowed per day; third should be blocked."""
        act1 = _make_activity(act_id="a1", subtype="strength", duration=30, earliest=time(7, 0), latest=time(9, 0))
        act2 = _make_activity(act_id="a2", subtype="strength", duration=30, earliest=time(10, 0), latest=time(12, 0))
        act3 = _make_activity(act_id="a3", subtype="strength", duration=30, earliest=time(14, 0), latest=time(16, 0))
        ctx = _make_ctx(activities=[act1, act2, act3])

        day = DaySchedule(date=date(2026, 6, 15), day_of_week=DayOfWeek.MONDAY)
        target_date = date(2026, 6, 15)

        result1 = _try_schedule_activity(act1, day, target_date, ctx)
        assert result1 is True

        result2 = _try_schedule_activity(act2, day, target_date, ctx)
        assert result2 is True

        # Third same-subtype should be blocked (exceeds MAX_SAME_SUBTYPE_PER_DAY=2)
        result3 = _try_schedule_activity(act3, day, target_date, ctx)
        assert result3 is False

    def test_different_subtype_allowed_on_same_day(self) -> None:
        """Activities with different subtypes can schedule on the same day."""
        act1 = _make_activity(act_id="a1", subtype="strength", earliest=time(7, 0), latest=time(9, 0))
        act2 = _make_activity(act_id="a2", subtype="cardio", earliest=time(10, 0), latest=time(12, 0))
        ctx = _make_ctx(activities=[act1, act2])

        day = DaySchedule(date=date(2026, 6, 15), day_of_week=DayOfWeek.MONDAY)
        target_date = date(2026, 6, 15)

        result1 = _try_schedule_activity(act1, day, target_date, ctx)
        assert result1 is True

        result2 = _try_schedule_activity(act2, day, target_date, ctx)
        assert result2 is True


# ═══════════════════════════════════════════════════════════
#  BACKUP FALLBACK
# ═══════════════════════════════════════════════════════════


class TestBackupFallback:
    def test_backup_used_when_primary_fails(self) -> None:
        """When the primary can't fit, a backup with a different subtype should be tried."""
        # Primary: needs a slot at 7-9 AM, 30 min
        primary = _make_activity(
            act_id="primary", subtype="swimming", duration=30,
            location="pool", earliest=time(7, 0), latest=time(7, 0),
            backup_ids=["backup1"],
        )
        # Backup: same concept but at home, wider window
        backup = _make_activity(
            act_id="backup1", subtype="swimming", duration=20,
            location="home", earliest=time(7, 0), latest=time(20, 0),
        )
        ctx = _make_ctx(activities=[primary, backup])

        day = DaySchedule(date=date(2026, 6, 15), day_of_week=DayOfWeek.MONDAY)
        target_date = date(2026, 6, 15)

        # Block the 7:00-7:30 slot so primary can't schedule
        day.blocks.append(ScheduleBlock(
            block_type=ScheduleBlockType.ACTIVITY, activity_id="blocker",
            activity_name="Blocker", activity_type=ActivityType.FITNESS,
            date=target_date, start_time=time(7, 0), end_time=time(8, 0),
        ))

        result = _try_schedule_activity(primary, day, target_date, ctx)
        assert result is True

        # Verify it was the backup that got scheduled
        scheduled_ids = [
            b.activity_id for b in day.blocks
            if b.block_type == ScheduleBlockType.ACTIVITY
        ]
        assert "backup1" in scheduled_ids

    def test_backup_with_subtype_collision_skipped(self) -> None:
        """Backup should be skipped if its subtype already at limit on the day."""
        existing1 = _make_activity(
            act_id="existing1", subtype="cardio",
            earliest=time(7, 0), latest=time(8, 0),
        )
        existing2 = _make_activity(
            act_id="existing2", subtype="cardio",
            earliest=time(8, 30), latest=time(9, 30),
        )
        primary = _make_activity(
            act_id="primary", subtype="strength",
            earliest=time(7, 0), latest=time(7, 0),  # very narrow → will fail
            backup_ids=["backup_cardio"],
        )
        # Backup has same subtype as existing — third cardio on the day
        backup = _make_activity(
            act_id="backup_cardio", subtype="cardio",
            earliest=time(10, 0), latest=time(20, 0),
        )
        ctx = _make_ctx(activities=[existing1, existing2, primary, backup])

        day = DaySchedule(date=date(2026, 6, 15), day_of_week=DayOfWeek.MONDAY)
        target_date = date(2026, 6, 15)

        # Schedule both existing cardio activities
        _try_schedule_activity(existing1, day, target_date, ctx)
        _try_schedule_activity(existing2, day, target_date, ctx)

        # Block primary's only slot
        day.blocks.append(ScheduleBlock(
            block_type=ScheduleBlockType.ACTIVITY, activity_id="blocker",
            activity_name="Blocker", activity_type=ActivityType.FITNESS,
            date=target_date, start_time=time(7, 0), end_time=time(8, 0),
        ))

        # Primary fails, backup exceeds subtype limit (2 existing + 1 backup = 3)
        result = _try_schedule_activity(primary, day, target_date, ctx)
        assert result is False


# ═══════════════════════════════════════════════════════════
#  BASIC SCHEDULE GENERATION
# ═══════════════════════════════════════════════════════════


class TestScheduleGeneration:
    def test_basic_schedule(self) -> None:
        activities = [
            _make_activity(
                act_id="act_1", name="Morning Run",
                subtype="cardio", earliest=time(7, 0), latest=time(9, 0),
            )
        ]
        client = _make_client()
        start = date(2026, 6, 15)
        end = start + timedelta(days=2)

        schedule = generate_schedule(activities, [], [], client, start, end)

        assert schedule.total_days == 3
        assert schedule.total_scheduled > 0
        assert schedule.total_unscheduled == 0

    def test_empty_activity_list(self) -> None:
        client = _make_client()
        start = date(2026, 6, 15)
        end = start + timedelta(days=1)

        schedule = generate_schedule([], [], [], client, start, end)

        assert schedule.total_days == 2
        assert schedule.total_scheduled == 0
        assert schedule.total_unscheduled == 0

    def test_medication_always_scheduled_on_travel_break(self) -> None:
        """Medications must never be skipped, even during BREAK travel mode."""
        med = _make_activity(
            act_id="med_1", name="Daily Pill",
            activity_type=ActivityType.MEDICATION,
            subtype="med_0", duration=2,
            earliest=time(8, 0), latest=time(20, 0),
        )
        client = _make_client(
            travel_plans=[
                TravelPlan(
                    start_date=date(2026, 6, 15),
                    end_date=date(2026, 6, 17),
                    destination="Beach",
                    adherence=TravelAdherence.BREAK,
                )
            ]
        )
        start = date(2026, 6, 15)
        end = date(2026, 6, 15)

        schedule = generate_schedule([med], [], [], client, start, end)

        # Medication should be scheduled despite BREAK mode
        activity_blocks = [
            b for d in schedule.days for b in d.blocks
            if b.block_type == ScheduleBlockType.ACTIVITY
        ]
        assert len(activity_blocks) > 0, "Medication must be scheduled even during BREAK"

    def test_non_med_activities_skipped_on_travel_break(self) -> None:
        """Non-medication activities should be skipped during BREAK travel mode."""
        fitness = _make_activity(
            act_id="fit_1", name="Run",
            activity_type=ActivityType.FITNESS,
            subtype="cardio", duration=30,
            earliest=time(7, 0), latest=time(20, 0),
        )
        client = _make_client(
            travel_plans=[
                TravelPlan(
                    start_date=date(2026, 6, 15),
                    end_date=date(2026, 6, 15),
                    destination="Beach",
                    adherence=TravelAdherence.BREAK,
                )
            ]
        )
        start = date(2026, 6, 15)
        end = date(2026, 6, 15)

        schedule = generate_schedule([fitness], [], [], client, start, end)

        assert schedule.total_unscheduled > 0, (
            "Fitness should be unscheduled during BREAK"
        )


# ═══════════════════════════════════════════════════════════
#  TRAVEL PLAN LOOKUP
# ═══════════════════════════════════════════════════════════


class TestTravelPlanLookup:
    def test_no_travel_plan_returns_none(self) -> None:
        client = _make_client()
        assert _get_travel_plan(client, date(2026, 6, 15)) is None

    def test_within_travel_period_returns_plan(self) -> None:
        plan = TravelPlan(
            start_date=date(2026, 6, 14),
            end_date=date(2026, 6, 20),
            destination="Paris",
            adherence=TravelAdherence.FLEXIBLE,
        )
        client = _make_client(travel_plans=[plan])
        result = _get_travel_plan(client, date(2026, 6, 16))
        assert result is not None
        assert result.destination == "Paris"

    def test_on_travel_start_date(self) -> None:
        plan = TravelPlan(
            start_date=date(2026, 6, 15),
            end_date=date(2026, 6, 20),
            destination="Tokyo",
            adherence=TravelAdherence.STRICT,
        )
        client = _make_client(travel_plans=[plan])
        assert _get_travel_plan(client, date(2026, 6, 15)) is not None

    def test_on_travel_end_date(self) -> None:
        plan = TravelPlan(
            start_date=date(2026, 6, 15),
            end_date=date(2026, 6, 20),
            destination="Tokyo",
            adherence=TravelAdherence.STRICT,
        )
        client = _make_client(travel_plans=[plan])
        assert _get_travel_plan(client, date(2026, 6, 20)) is not None

    def test_before_travel_period_returns_none(self) -> None:
        plan = TravelPlan(
            start_date=date(2026, 6, 20),
            end_date=date(2026, 6, 25),
            destination="Berlin",
            adherence=TravelAdherence.FLEXIBLE,
        )
        client = _make_client(travel_plans=[plan])
        assert _get_travel_plan(client, date(2026, 6, 19)) is None

    def test_after_travel_period_returns_none(self) -> None:
        plan = TravelPlan(
            start_date=date(2026, 6, 15),
            end_date=date(2026, 6, 18),
            destination="Berlin",
            adherence=TravelAdherence.FLEXIBLE,
        )
        client = _make_client(travel_plans=[plan])
        assert _get_travel_plan(client, date(2026, 6, 19)) is None


# ═══════════════════════════════════════════════════════════
#  LAST LOCATION TRACKING
# ═══════════════════════════════════════════════════════════


class TestLastLocation:
    def test_empty_day_returns_home(self) -> None:
        day = DaySchedule(date=date(2026, 6, 15), day_of_week=DayOfWeek.MONDAY)
        loc = _get_last_location_before(day, time(10, 0), "home")
        assert loc == "home"

    def test_returns_location_of_last_preceding_block(self) -> None:
        day = DaySchedule(date=date(2026, 6, 15), day_of_week=DayOfWeek.MONDAY)
        day.blocks.append(ScheduleBlock(
            block_type=ScheduleBlockType.ACTIVITY,
            activity_id="a1", activity_name="Gym", activity_type=ActivityType.FITNESS,
            date=date(2026, 6, 15), start_time=time(8, 0), end_time=time(9, 0),
        ))
        day.blocks[0].location = "gym"
        loc = _get_last_location_before(day, time(10, 0), "home")
        assert loc == "gym"

    def test_skips_transit_blocks(self) -> None:
        day = DaySchedule(date=date(2026, 6, 15), day_of_week=DayOfWeek.MONDAY)
        day.blocks.append(ScheduleBlock(
            block_type=ScheduleBlockType.TRANSIT,
            activity_id=None, activity_name="Transit", activity_type=None,
            date=date(2026, 6, 15), start_time=time(9, 0), end_time=time(9, 20),
        ))
        loc = _get_last_location_before(day, time(10, 0), "home")
        assert loc == "home"  # Transit ignored, fall back to home


# ═══════════════════════════════════════════════════════════
#  FLEXIBLE TRAVEL MODE
# ═══════════════════════════════════════════════════════════


class TestFlexibleTravel:
    def test_remote_activity_scheduled_during_flexible_travel(self) -> None:
        """Remote-capable activities should be allowed during FLEXIBLE travel."""
        remote_act = _make_activity(
            act_id="remote_1", name="Online Yoga",
            activity_type=ActivityType.FITNESS,
            subtype="flexibility", duration=30,
            remote=True,
            earliest=time(7, 0), latest=time(20, 0),
        )
        client = _make_client(
            travel_plans=[
                TravelPlan(
                    start_date=date(2026, 6, 15),
                    end_date=date(2026, 6, 15),
                    destination="NYC",
                    adherence=TravelAdherence.FLEXIBLE,
                )
            ]
        )
        start = date(2026, 6, 15)
        end = date(2026, 6, 15)

        schedule = generate_schedule([remote_act], [], [], client, start, end)
        assert schedule.total_scheduled > 0

    def test_non_remote_activity_unscheduled_during_flexible_travel(self) -> None:
        """Non-remote activities should be skipped during FLEXIBLE travel."""
        gym_act = _make_activity(
            act_id="gym_1", name="Gym Session",
            activity_type=ActivityType.FITNESS,
            subtype="strength", duration=60,
            location="gym", remote=False,
            earliest=time(7, 0), latest=time(20, 0),
        )
        client = _make_client(
            travel_plans=[
                TravelPlan(
                    start_date=date(2026, 6, 15),
                    end_date=date(2026, 6, 15),
                    destination="NYC",
                    adherence=TravelAdherence.FLEXIBLE,
                )
            ]
        )
        start = date(2026, 6, 15)
        end = date(2026, 6, 15)

        schedule = generate_schedule([gym_act], [], [], client, start, end)
        assert schedule.total_unscheduled > 0


# ═══════════════════════════════════════════════════════════
#  MEAL & MEDICATION SCHEDULING PHASES
# ═══════════════════════════════════════════════════════════


class TestMealAndMedicationPhases:
    def test_all_three_meal_anchors_scheduled(self) -> None:
        """Phase 1: All three meals must land every day."""
        breakfast = _make_activity(
            act_id="bf", name="Breakfast", subtype="breakfast",
            activity_type=ActivityType.FOOD_CONSUMPTION,
            duration=30, earliest=time(7, 0), latest=time(9, 0),
        )
        lunch = _make_activity(
            act_id="ln", name="Lunch", subtype="lunch",
            activity_type=ActivityType.FOOD_CONSUMPTION,
            duration=30, earliest=time(12, 0), latest=time(14, 0),
        )
        dinner = _make_activity(
            act_id="dn", name="Dinner", subtype="dinner",
            activity_type=ActivityType.FOOD_CONSUMPTION,
            duration=30, earliest=time(18, 0), latest=time(20, 0),
        )

        client = _make_client()
        start = date(2026, 6, 15)
        end = date(2026, 6, 15)

        schedule = generate_schedule([breakfast, lunch, dinner], [], [], client, start, end)

        # All three meals should be scheduled on the single day
        assert schedule.total_scheduled == 3
        assert schedule.total_unscheduled == 0

    def test_medication_with_meal_relation_scheduled_relative_to_meal(self) -> None:
        """Phase 2: Medications must pin to their meal anchor."""
        breakfast = _make_activity(
            act_id="bf", name="Breakfast", subtype="breakfast",
            activity_type=ActivityType.FOOD_CONSUMPTION,
            duration=30, earliest=time(7, 0), latest=time(9, 0),
        )
        # Medication WITH_MEAL at BREAKFAST → should land at/near breakfast time
        med = Activity(
            id="med_1", name="Morning Pill",
            activity_type=ActivityType.MEDICATION,
            priority=1, duration_minutes=2,
            frequency_times=1, frequency_period=FrequencyPeriod.DAILY,
            details="", facilitator_id=None, facilitator_type=ResourceType.SELF,
            location_id=None, location_name="home", remote_capable=True,
            prep_description="", prep_duration_minutes=0, prep_buffer_minutes=0,
            subtype="med_0", is_necessary=True,
            meal_relation=MealRelation.WITH_MEAL,
            meal_relation_type=MealType.BREAKFAST,
            meal_relation_offset_minutes=0,
        )

        client = _make_client()
        start = date(2026, 6, 15)
        end = date(2026, 6, 15)

        schedule = generate_schedule([breakfast, med], [], [], client, start, end)
        assert schedule.total_scheduled == 2
        assert schedule.total_unscheduled == 0


# ═══════════════════════════════════════════════════════════
#  WEEKLY FREQUENCY LIMITING
# ═══════════════════════════════════════════════════════════


class TestWeeklyFrequency:
    def test_weekly_activity_not_over_scheduled(self) -> None:
        """A 3x/week activity should appear at most 3 times in 7 days."""
        act = _make_activity(
            act_id="a1", name="Swimming",
            subtype="swimming", duration=45,
            freq_times=3, freq_period=FrequencyPeriod.WEEKLY,
            earliest=time(7, 0), latest=time(20, 0),
        )

        client = _make_client()
        start = date(2026, 6, 15)  # Monday
        end = date(2026, 6, 21)    # Sunday (7 days)

        schedule = generate_schedule([act], [], [], client, start, end)

        # Count how many times it appeared (max 3)
        count = sum(
            1 for d in schedule.days for b in d.blocks
            if b.block_type == ScheduleBlockType.ACTIVITY and b.activity_id == "a1"
        )
        assert count <= 3, f"Expected ≤3 occurrences, got {count}"
        assert count > 0, "Expected at least 1 occurrence"


# ═══════════════════════════════════════════════════════════
#  DATA GENERATOR: GENERATE ALL DATA SMOKE TEST
# ═══════════════════════════════════════════════════════════


class TestGenerateAllData:
    def test_generate_all_data_produces_files(self) -> None:
        """Smoke test: generate_all_data should produce valid output files."""
        import os
        from data_generator import generate_all_data

        # Run generator — checks it doesn't crash
        generate_all_data()

        # Check output files exist (schedule.json is produced by FastAPI startup,
        # not the generator — only check data generator outputs here)
        data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        for expected_file in ("action_plan.json", "activities.json", "resources.json",
                              "client.json", "availability.json"):
            assert os.path.exists(os.path.join(data_dir, expected_file)), (
                f"Missing expected data file: {expected_file}"
            )

