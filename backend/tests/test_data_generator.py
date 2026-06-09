import pytest
from backend.data_generator import load_templates, generate_resources, generate_activities
from backend.models import ActivityType

def test_generate_resources():
    templates = load_templates()
    resources = generate_resources(templates)
    assert len(resources) > 0
    # Check that we have different types of resources
    types = {r.resource_type for r in resources}
    assert "SPECIALIST" in [t.value for t in types]
    assert "LOCATION" in [t.value for t in types]

def test_generate_activities():
    templates = load_templates()
    resources = generate_resources(templates)
    activities = generate_activities(templates, resources)
    
    # We should have a curated action plan with ~25 activities, plus backups
    assert len(activities) > 20
    
    action_plan = [a for a in activities if not a.is_backup_only]
    backups = [a for a in activities if a.is_backup_only]
    
    assert len(action_plan) > 0
    assert len(backups) > 0
    
    # Check that there are medications in the action plan
    meds = [a for a in action_plan if a.activity_type == ActivityType.MEDICATION]
    assert len(meds) > 0

    # Ensure backups have the flag set correctly
    for a in backups:
        assert a.is_backup_only is True
