# AGENT-MODIFIED: Comprehensive tests for data generator
"""
Tests for the data generation pipeline.

Covers:
  - Resource generation from templates
  - Activity generation (50+ with variants)
  - Action plan curation (exactly 22)
  - Necessary vs optional subtype selection
  - Backup activity wiring
  - Variant activity_type preservation
"""

import pytest
from data_generator import (
    load_templates,
    generate_resources,
    generate_activities,
)
from models import ActivityType, FrequencyPeriod, ResourceType


@pytest.fixture
def templates():
    """Load templates once for all tests."""
    return load_templates()


@pytest.fixture
def resources(templates):
    """Generate resources once for all tests."""
    return generate_resources(templates)


@pytest.fixture
def generated(templates, resources):
    """Generate all activities and plan_ids."""
    return generate_activities(templates, resources)


# ═══════════════════════════════════════════════════════════
#  RESOURCE GENERATION
# ═══════════════════════════════════════════════════════════


class TestResourceGeneration:
    def test_resources_not_empty(self, resources):
        assert len(resources) > 0

    def test_all_required_resource_types_present(self, resources):
        types = {r.resource_type for r in resources}
        expected = {
            ResourceType.SPECIALIST,
            ResourceType.ALLIED_HEALTH,
            ResourceType.TRAINER,
            ResourceType.EQUIPMENT,
            ResourceType.LOCATION,
        }
        assert expected.issubset(types)

    def test_resources_have_valid_ids(self, resources):
        ids = [r.id for r in resources]
        assert len(ids) == len(set(ids)), "Resource IDs must be unique"
        for rid in ids:
            assert rid, "Resource ID must not be empty"


# ═══════════════════════════════════════════════════════════
#  ACTIVITY GENERATION
# ═══════════════════════════════════════════════════════════


class TestActivityGeneration:
    def test_generates_50_plus_activities(self, generated):
        activities, _ = generated
        assert len(activities) >= 50, (
            f"Expected 50+ activities, got {len(activities)}"
        )

    def test_all_five_activity_types_present(self, generated):
        activities, _ = generated
        types = {a.activity_type for a in activities}
        for at in ActivityType:
            assert at in types, f"Missing activity type: {at.value}"

    def test_variant_activity_type_preserved(self, generated):
        """Variants must inherit the base activity's type, not be hardcoded FITNESS."""
        activities, _ = generated
        variants = [a for a in activities if "- Beginner" in a.name or "- Advanced" in a.name]
        assert len(variants) > 0, "Should have generated variants"

        for v in variants:
            # Find the base name (strip suffix)
            base_name = v.name.split(" - ")[0]
            base = next((a for a in activities if a.name == base_name), None)
            if base:
                assert v.activity_type == base.activity_type, (
                    f"Variant '{v.name}' has type {v.activity_type.value} "
                    f"but base '{base.name}' has type {base.activity_type.value}"
                )

    def test_all_activities_have_subtype(self, generated):
        activities, _ = generated
        for act in activities:
            assert act.subtype, f"Activity '{act.name}' has empty subtype"

    def test_unique_activity_ids(self, generated):
        activities, _ = generated
        ids = [a.id for a in activities]
        assert len(ids) == len(set(ids)), "Activity IDs must be unique"


# ═══════════════════════════════════════════════════════════
#  ACTION PLAN CURATION
# ═══════════════════════════════════════════════════════════


class TestActionPlanCuration:
    def test_exactly_26_activities(self, generated):
        activities, plan_ids = generated
        assert len(plan_ids) == 26

    def test_all_8_medications_present(self, generated):
        """All medications are marked is_necessary=True and must all appear."""
        activities, plan_ids = generated
        action_plan = [a for a in activities if a.id in plan_ids]
        meds = [a for a in action_plan if a.activity_type == ActivityType.MEDICATION]
        assert len(meds) == 8, (
            f"Expected all 8 medications in action plan, got {len(meds)}: "
            f"{[m.name for m in meds]}"
        )

    def test_all_3_meal_anchors_present(self, generated):
        """Breakfast, lunch, dinner must all appear (necessary subtypes)."""
        activities, plan_ids = generated
        action_plan = [a for a in activities if a.id in plan_ids]
        meal_subtypes = {
            a.subtype for a in action_plan
            if a.subtype in ("breakfast", "lunch", "dinner")
        }
        assert meal_subtypes == {"breakfast", "lunch", "dinner"}, (
            f"Missing meal anchors: {{'breakfast','lunch','dinner'}} - {meal_subtypes}"
        )

    def test_necessary_subtypes_have_exactly_one(self, generated):
        """Each necessary subtype must have exactly 1 representative."""
        activities, plan_ids = generated
        action_plan = [a for a in activities if a.id in plan_ids]
        necessary = [a for a in action_plan if a.is_necessary]
        necessary_subtypes = [a.subtype for a in necessary]
        # Each should appear exactly once
        for subtype in set(necessary_subtypes):
            count = necessary_subtypes.count(subtype)
            assert count == 1, (
                f"Necessary subtype '{subtype}' has {count} entries (expected 1)"
            )

    def test_optional_dual_variants_frequency_constraint(self, generated):
        """If two variants of the same optional subtype are picked,
        neither should be DAILY and their combined frequency must be <= 7."""
        activities, plan_ids = generated
        action_plan = [a for a in activities if a.id in plan_ids]
        optional = [a for a in action_plan if not a.is_necessary]
        subtype_groups: dict[str, list] = {}
        for a in optional:
            subtype_groups.setdefault(a.subtype, []).append(a)

        for subtype, acts in subtype_groups.items():
            if len(acts) > 1:
                for act in acts:
                    assert act.frequency_period != FrequencyPeriod.DAILY, (
                        f"Dual-variant subtype '{subtype}' has a DAILY activity: {act.name}"
                    )
                total_freq = sum(a.frequency_times for a in acts)
                assert total_freq <= 7, (
                    f"Dual-variant subtype '{subtype}' has combined frequency {total_freq} > 7"
                )


# ═══════════════════════════════════════════════════════════
#  BACKUP WIRING
# ═══════════════════════════════════════════════════════════


class TestBackupWiring:
    def test_action_plan_activities_have_backups(self, generated):
        """Activities with same-subtype variants should have backup IDs."""
        activities, plan_ids = generated
        action_plan = [a for a in activities if a.id in plan_ids]
        has_backups = [a for a in action_plan if a.backup_activity_ids]
        # At least some should have backups (meals, fitness, etc.)
        assert len(has_backups) > 0, "No activities have backup_activity_ids"

    def test_medications_have_no_backups(self, generated):
        """Medications have unique subtypes (med_0..med_7), so no backups possible."""
        activities, plan_ids = generated
        action_plan = [a for a in activities if a.id in plan_ids]
        meds = [a for a in action_plan if a.activity_type == ActivityType.MEDICATION]
        for med in meds:
            assert len(med.backup_activity_ids) == 0, (
                f"Medication '{med.name}' should not have backups, got {med.backup_activity_ids}"
            )

    def test_backup_ids_reference_valid_activities(self, generated):
        """All backup IDs must reference activities in the full pool."""
        activities, plan_ids = generated
        action_plan = [a for a in activities if a.id in plan_ids]
        all_ids = {a.id for a in activities}
        for act in action_plan:
            for backup_id in act.backup_activity_ids:
                assert backup_id in all_ids, (
                    f"Backup ID '{backup_id}' for '{act.name}' not found in activity pool"
                )

    def test_backup_ids_share_subtype_with_parent(self, generated):
        """Backup activities must have the same subtype as the parent."""
        activities, plan_ids = generated
        action_plan = [a for a in activities if a.id in plan_ids]
        activity_map = {a.id: a for a in activities}
        for act in action_plan:
            for backup_id in act.backup_activity_ids:
                backup = activity_map[backup_id]
                assert backup.subtype == act.subtype, (
                    f"Backup '{backup.name}' has subtype '{backup.subtype}' "
                    f"but parent '{act.name}' has subtype '{act.subtype}'"
                )
