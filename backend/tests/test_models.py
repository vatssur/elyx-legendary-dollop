import pytest
from datetime import date, time
from backend.models import (
    Activity, ActivityType, FrequencyPeriod, MealRelation, MealType,
    ScheduleBlock, ScheduleBlockType, DaySchedule, FullSchedule
)

def test_activity_creation():
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
        facilitator_type="SELF",
        location_id=None,
        location_name="home",
        remote_capable=True,
        prep_description="",
        prep_duration_minutes=0,
        prep_buffer_minutes=0,
    )
    assert act.id == "act_001"
    assert act.is_backup_only is False
    assert act.activity_type == ActivityType.FITNESS

def test_schedule_block_duration():
    block = ScheduleBlock(
        block_type=ScheduleBlockType.ACTIVITY,
        activity_id="act_001",
        activity_name="Test",
        activity_type=ActivityType.FITNESS,
        date=date(2026, 6, 15),
        start_time=time(10, 0),
        end_time=time(10, 45)
    )
    assert block.duration_minutes == 45
    assert block.color_code == "#4CAF50"  # FITNESS color

def test_full_schedule_metrics():
    sched = FullSchedule(start_date=date(2026,6,15), end_date=date(2026,6,16))
    
    day = DaySchedule(date=date(2026,6,15), day_of_week="MONDAY")
    day.blocks.append(ScheduleBlock(
        block_type=ScheduleBlockType.ACTIVITY,
        activity_id="a1", activity_name="A1", activity_type=ActivityType.FITNESS,
        date=date(2026,6,15), start_time=time(9,0), end_time=time(10,0)
    ))
    # Prep block shouldn't count in total_scheduled
    day.blocks.append(ScheduleBlock(
        block_type=ScheduleBlockType.PREP,
        activity_id=None, activity_name="Prep", activity_type=None,
        date=date(2026,6,15), start_time=time(8,45), end_time=time(9,0)
    ))
    sched.days.append(day)
    
    assert sched.total_days == 1
    assert sched.total_scheduled == 1
