# AGENT-MODIFIED: Comprehensive model tests
"""
Tests for core data models in models.py.

Covers:
  - Activity creation with all required fields
  - Default field values (backup_activity_ids, subtype, metrics, etc.)
  - ScheduleBlock duration calculation and color codes
  - FullSchedule aggregate metrics
  - Enum completeness
"""

import pytest
from datetime import date, time
from models import (
    Activity,
    ActivityType,
    FrequencyPeriod,
    MealRelation,
    MealType,
    ResourceType,
    ScheduleBlock,
    ScheduleBlockType,
    DayOfWeek,
    DaySchedule,
    FullSchedule,
    UnscheduledActivity,
    ACTIVITY_COLOR_MAP,
    BLOCK_TYPE_COLOR_MAP,
)


# ═══════════════════════════════════════════════════════════
#  ACTIVITY DATACLASS
# ═══════════════════════════════════════════════════════════


class TestActivity:
    def test_creation_with_required_fields(self):
        act = Activity(
            id="act_001",
            name="Test Activity",
            activity_type=ActivityType.FITNESS,
            priority=1,
            duration_minutes=30,
            frequency_times=3,
            frequency_period=FrequencyPeriod.WEEKLY,
            details="Test details",
            facilitator_id=None,
            facilitator_type=ResourceType.SELF,
            location_id=None,
            location_name="home",
            remote_capable=True,
            prep_description="",
            prep_duration_minutes=0,
            prep_buffer_minutes=0,
        )
        assert act.id == "act_001"
        assert act.activity_type == ActivityType.FITNESS

    def test_default_backup_activity_ids(self):
        act = Activity(
            id="act_001", name="Test", activity_type=ActivityType.FITNESS,
            priority=1, duration_minutes=30, frequency_times=1,
            frequency_period=FrequencyPeriod.DAILY, details="",
            facilitator_id=None, facilitator_type=ResourceType.SELF,
            location_id=None, location_name="home", remote_capable=False,
            prep_description="", prep_duration_minutes=0, prep_buffer_minutes=0,
        )
        assert act.backup_activity_ids == []

    def test_default_subtype_and_is_necessary(self):
        act = Activity(
            id="act_001", name="Test", activity_type=ActivityType.FITNESS,
            priority=1, duration_minutes=30, frequency_times=1,
            frequency_period=FrequencyPeriod.DAILY, details="",
            facilitator_id=None, facilitator_type=ResourceType.SELF,
            location_id=None, location_name="home", remote_capable=False,
            prep_description="", prep_duration_minutes=0, prep_buffer_minutes=0,
        )
        assert act.subtype == ""
        assert act.is_necessary is False

    def test_default_metrics_is_empty_list(self):
        act = Activity(
            id="act_001", name="Test", activity_type=ActivityType.FITNESS,
            priority=1, duration_minutes=30, frequency_times=1,
            frequency_period=FrequencyPeriod.DAILY, details="",
            facilitator_id=None, facilitator_type=ResourceType.SELF,
            location_id=None, location_name="home", remote_capable=False,
            prep_description="", prep_duration_minutes=0, prep_buffer_minutes=0,
        )
        assert act.metrics == []

    def test_default_meal_relation(self):
        act = Activity(
            id="act_001", name="Test", activity_type=ActivityType.MEDICATION,
            priority=1, duration_minutes=2, frequency_times=1,
            frequency_period=FrequencyPeriod.DAILY, details="",
            facilitator_id=None, facilitator_type=ResourceType.SELF,
            location_id=None, location_name="home", remote_capable=True,
            prep_description="", prep_duration_minutes=0, prep_buffer_minutes=0,
        )
        assert act.meal_relation == MealRelation.NONE
        assert act.meal_relation_type == MealType.ANY
        assert act.meal_relation_offset_minutes == 0

    def test_backup_activity_ids_can_be_set(self):
        act = Activity(
            id="act_001", name="Test", activity_type=ActivityType.FITNESS,
            priority=1, duration_minutes=30, frequency_times=1,
            frequency_period=FrequencyPeriod.DAILY, details="",
            facilitator_id=None, facilitator_type=ResourceType.SELF,
            location_id=None, location_name="home", remote_capable=False,
            prep_description="", prep_duration_minutes=0, prep_buffer_minutes=0,
            backup_activity_ids=["act_002", "act_003"],
        )
        assert act.backup_activity_ids == ["act_002", "act_003"]

    def test_default_list_fields_are_independent(self):
        """Ensure default_factory creates independent lists per instance."""
        a1 = Activity(
            id="act_001", name="A1", activity_type=ActivityType.FITNESS,
            priority=1, duration_minutes=30, frequency_times=1,
            frequency_period=FrequencyPeriod.DAILY, details="",
            facilitator_id=None, facilitator_type=ResourceType.SELF,
            location_id=None, location_name="home", remote_capable=False,
            prep_description="", prep_duration_minutes=0, prep_buffer_minutes=0,
        )
        a2 = Activity(
            id="act_002", name="A2", activity_type=ActivityType.FITNESS,
            priority=2, duration_minutes=30, frequency_times=1,
            frequency_period=FrequencyPeriod.DAILY, details="",
            facilitator_id=None, facilitator_type=ResourceType.SELF,
            location_id=None, location_name="home", remote_capable=False,
            prep_description="", prep_duration_minutes=0, prep_buffer_minutes=0,
        )
        a1.backup_activity_ids.append("act_999")
        assert a2.backup_activity_ids == [], "Default lists must be independent"


# ═══════════════════════════════════════════════════════════
#  SCHEDULE BLOCK
# ═══════════════════════════════════════════════════════════


class TestScheduleBlock:
    def test_duration_minutes(self):
        block = ScheduleBlock(
            block_type=ScheduleBlockType.ACTIVITY,
            activity_id="act_001",
            activity_name="Test",
            activity_type=ActivityType.FITNESS,
            date=date(2026, 6, 15),
            start_time=time(10, 0),
            end_time=time(10, 45),
        )
        assert block.duration_minutes == 45

    def test_activity_color_code(self):
        block = ScheduleBlock(
            block_type=ScheduleBlockType.ACTIVITY,
            activity_id="act_001",
            activity_name="Test",
            activity_type=ActivityType.FITNESS,
            date=date(2026, 6, 15),
            start_time=time(10, 0),
            end_time=time(10, 45),
        )
        assert block.color_code == "#4CAF50"

    def test_prep_color_code(self):
        block = ScheduleBlock(
            block_type=ScheduleBlockType.PREP,
            activity_id=None,
            activity_name="Prep",
            activity_type=None,
            date=date(2026, 6, 15),
            start_time=time(9, 0),
            end_time=time(9, 15),
        )
        assert block.color_code == BLOCK_TYPE_COLOR_MAP[ScheduleBlockType.PREP]

    def test_transit_color_code(self):
        block = ScheduleBlock(
            block_type=ScheduleBlockType.TRANSIT,
            activity_id=None,
            activity_name="Transit",
            activity_type=None,
            date=date(2026, 6, 15),
            start_time=time(9, 0),
            end_time=time(9, 20),
        )
        assert block.color_code == BLOCK_TYPE_COLOR_MAP[ScheduleBlockType.TRANSIT]

    def test_unique_block_ids(self):
        b1 = ScheduleBlock(
            block_type=ScheduleBlockType.ACTIVITY, activity_id="a",
            activity_name="A", activity_type=ActivityType.FITNESS,
            date=date(2026, 6, 15), start_time=time(9, 0), end_time=time(10, 0),
        )
        b2 = ScheduleBlock(
            block_type=ScheduleBlockType.ACTIVITY, activity_id="b",
            activity_name="B", activity_type=ActivityType.FITNESS,
            date=date(2026, 6, 15), start_time=time(10, 0), end_time=time(11, 0),
        )
        assert b1.block_id != b2.block_id


# ═══════════════════════════════════════════════════════════
#  FULL SCHEDULE METRICS
# ═══════════════════════════════════════════════════════════


class TestFullSchedule:
    def test_total_days(self):
        sched = FullSchedule(start_date=date(2026, 6, 15), end_date=date(2026, 6, 16))
        sched.days.append(DaySchedule(date=date(2026, 6, 15), day_of_week=DayOfWeek.MONDAY))
        assert sched.total_days == 1

    def test_total_scheduled_only_counts_activities(self):
        sched = FullSchedule(start_date=date(2026, 6, 15), end_date=date(2026, 6, 16))
        day = DaySchedule(date=date(2026, 6, 15), day_of_week=DayOfWeek.MONDAY)
        day.blocks.append(ScheduleBlock(
            block_type=ScheduleBlockType.ACTIVITY, activity_id="a1",
            activity_name="A1", activity_type=ActivityType.FITNESS,
            date=date(2026, 6, 15), start_time=time(9, 0), end_time=time(10, 0),
        ))
        day.blocks.append(ScheduleBlock(
            block_type=ScheduleBlockType.PREP, activity_id=None,
            activity_name="Prep", activity_type=None,
            date=date(2026, 6, 15), start_time=time(8, 45), end_time=time(9, 0),
        ))
        day.blocks.append(ScheduleBlock(
            block_type=ScheduleBlockType.TRANSIT, activity_id=None,
            activity_name="Transit", activity_type=None,
            date=date(2026, 6, 15), start_time=time(8, 30), end_time=time(8, 45),
        ))
        sched.days.append(day)
        assert sched.total_scheduled == 1  # Only ACTIVITY blocks count

    def test_total_unscheduled(self):
        sched = FullSchedule(start_date=date(2026, 6, 15), end_date=date(2026, 6, 16))
        sched.unscheduled.append(UnscheduledActivity(
            activity_id="a1", activity_name="A1",
            activity_type=ActivityType.FITNESS,
            target_date=date(2026, 6, 15),
            reason="No slot", adjustment="Add tomorrow",
        ))
        assert sched.total_unscheduled == 1

    def test_empty_schedule_metrics(self):
        sched = FullSchedule(start_date=date(2026, 6, 15), end_date=date(2026, 6, 16))
        assert sched.total_days == 0
        assert sched.total_scheduled == 0
        assert sched.total_unscheduled == 0


# ═══════════════════════════════════════════════════════════
#  ENUM COMPLETENESS
# ═══════════════════════════════════════════════════════════


class TestEnums:
    def test_all_activity_types_have_colors(self):
        for at in ActivityType:
            assert at in ACTIVITY_COLOR_MAP, f"Missing color for {at.value}"

    def test_all_block_types_have_colors(self):
        """ACTIVITY gets its color from activity_type, so only non-ACTIVITY types need colors."""
        for bt in ScheduleBlockType:
            if bt == ScheduleBlockType.ACTIVITY:
                continue
            assert bt in BLOCK_TYPE_COLOR_MAP, f"Missing color for {bt.value}"

    def test_frequency_periods(self):
        assert len(list(FrequencyPeriod)) == 3

    def test_meal_relations(self):
        assert len(list(MealRelation)) == 4

    def test_travel_adherence_levels(self):
        from models import TravelAdherence
        assert len(list(TravelAdherence)) == 3
