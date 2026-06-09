import pytest
from datetime import date, time, timedelta
from backend.models import (
    Activity, ActivityType, FrequencyPeriod, Resource, ResourceType, 
    ClientAvailability, TravelPlan, TravelAdherence, DayOfWeek
)
from backend.scheduler import generate_schedule, _find_slot, _infer_meal_type, MealType

def test_infer_meal_type():
    class DummyAct:
        name = ""
    
    act = DummyAct()
    act.name = "Breakfast"
    assert _infer_meal_type(act) == MealType.BREAKFAST
    
    act.name = "Lunch"
    assert _infer_meal_type(act) == MealType.LUNCH
    
    act.name = "Dinner"
    assert _infer_meal_type(act) == MealType.DINNER
    
    act.name = "Snack"
    assert _infer_meal_type(act) == MealType.ANY

def test_generate_schedule():
    # Simple test to ensure the scheduler runs without crashing on minimal data
    activities = [
        Activity(
            id="act_1",
            name="Morning Run",
            activity_type=ActivityType.FITNESS,
            priority=1,
            duration_minutes=30,
            frequency_times=1,
            frequency_period=FrequencyPeriod.DAILY,
            details="",
            facilitator_id=None,
            facilitator_type=ResourceType.SELF,
            location_id="loc_home",
            location_name="home",
            remote_capable=True,
            prep_description="",
            prep_duration_minutes=0,
            prep_buffer_minutes=0,
            earliest_start=time(7,0),
            latest_start=time(9,0)
        )
    ]
    
    resources = []
    availability = []
    
    client = ClientAvailability(
        client_id="client_1",
        sleep_start=time(22, 0),
        sleep_end=time(6, 0),
        work_start=time(9, 0),
        work_end=time(17, 0)
    )
    
    start_date = date(2026, 6, 15)
    end_date = start_date + timedelta(days=2)
    
    schedule = generate_schedule(activities, resources, availability, client, start_date, end_date)
    
    assert schedule.total_days == 3
    # Check that Morning Run was scheduled
    assert schedule.total_scheduled > 0
    assert schedule.total_unscheduled == 0
