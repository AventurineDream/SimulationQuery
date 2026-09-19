from datetime import datetime, timedelta, timezone

import pytest

from improv_troupe.domain import (
    CastMember,
    DomainStateError,
    OpeningSnapshot,
    Season,
    SeasonStatus,
    arm_season,
    diary_cutoff_at,
    format_delay,
    generate_schedule,
    next_0600_pacific,
    next_season_id,
    transition_season,
)


def _green(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _draft() -> Season:
    return Season(season_id="S01", season_number=1)


def _opening() -> OpeningSnapshot:
    return OpeningSnapshot(
        set="The Observatory",
        setting="A remote orbital station",
        cast=["MARA", "JONAS"],
        world_rules=["The station remembers spoken promises."],
    )


def test_production_plan_schema_version_remains_distinct_from_season_schema():
    from improv_troupe.domain import SCHEMA_VERSION, SEASON_SCHEMA_VERSION

    assert SCHEMA_VERSION == "1.0"
    assert SEASON_SCHEMA_VERSION == "1.0"


def test_next_boundary_before_and_after_six_pacific():
    before = _green("2026-08-20T05:59:00-07:00")
    after = _green("2026-08-20T06:01:00-07:00")
    assert next_0600_pacific(before).isoformat() == "2026-08-20T06:00:00-07:00"
    assert next_0600_pacific(after).isoformat() == "2026-08-21T06:00:00-07:00"


def test_schedule_has_exactly_21_unique_slots_and_original_metadata():
    slots = generate_schedule("S01", _green("2026-08-20T07:00:00-07:00"))
    assert len(slots) == 21
    assert len({slot.slot_id for slot in slots}) == 21
    assert [slot.run_number for slot in slots] == list(range(1, 22))
    assert slots[0].scheduled_local.isoformat() == "2026-08-21T06:00:00-07:00"
    assert slots[0].utc_offset == "-07:00"
    assert slots[-1].day_number == 7
    assert slots[-1].slot_number == 3


def test_schedule_preserves_pst_and_pdt_across_dst_fall_back():
    slots = generate_schedule("S01", _green("2026-10-30T20:00:00-07:00"))
    dst_morning = slots[3]
    assert dst_morning.scheduled_local.isoformat() == "2026-11-01T06:00:00-08:00"
    assert dst_morning.utc_offset == "-08:00"
    assert dst_morning.scheduled_utc == datetime(
        2026, 11, 1, 14, tzinfo=timezone.utc
    )


def test_opening_creator_view_contains_only_four_opening_fields():
    opening = _opening()
    assert set(opening.creator_view()) == {"set", "setting", "cast", "world_rules"}


def test_state_transitions_reject_invalid_transition():
    with pytest.raises(DomainStateError):
        transition_season(_draft(), SeasonStatus.RUNNING)
    awaiting = transition_season(_draft(), SeasonStatus.AWAITING_GREEN)
    awaiting = awaiting.model_copy(update={"preflight_passed": True})
    armed = arm_season(
        awaiting,
        green_at=_green("2026-08-20T07:00:00-07:00"),
        opening=_opening(),
        cast=[CastMember(character_id="mara", name="MARA"), CastMember(character_id="jonas", name="JONAS")],
    )
    assert armed.status is SeasonStatus.ARMED
    assert armed.start_date == _green("2026-08-21T06:00:00-07:00").date()
    assert len(armed.schedule) == 21


def test_only_one_nonterminal_season_can_be_active():
    first = Season(season_id="S01", season_number=1, status=SeasonStatus.ARMED)
    second = Season(season_id="S02", season_number=2, status=SeasonStatus.ARMED)
    with pytest.raises(DomainStateError):
        arm_season(
            transition_season(
                Season(season_id="S03", season_number=3), SeasonStatus.AWAITING_GREEN
            ).model_copy(update={"preflight_passed": True}),
            green_at=_green("2026-08-20T07:00:00-07:00"),
            opening=_opening(),
            cast=[CastMember(character_id="mara", name="MARA"), CastMember(character_id="jonas", name="JONAS")],
            existing_seasons=[first, second],
        )


def test_one_existing_active_season_also_blocks_a_new_season():
    existing = Season(season_id="S01", season_number=1, status=SeasonStatus.ARMED)
    with pytest.raises(DomainStateError, match="active season already exists"):
        arm_season(
            transition_season(
                Season(season_id="S02", season_number=2), SeasonStatus.AWAITING_GREEN
            ).model_copy(update={"preflight_passed": True}),
            green_at=_green("2026-08-20T07:00:00-07:00"),
            opening=_opening(),
            cast=[CastMember(character_id="mara", name="MARA"), CastMember(character_id="jonas", name="JONAS")],
            existing_seasons=[existing],
        )


def test_schedule_slot_rejects_wrong_pacific_wall_clock_time():
    slots = generate_schedule("S01", _green("2026-08-20T07:00:00-07:00"))
    with pytest.raises(ValueError, match="Pacific wall-clock"):
        type(slots[0]).model_validate(
            {
                **slots[0].model_dump(),
                "scheduled_local": slots[0].scheduled_local.replace(hour=7),
            }
        )


def test_diary_cutoff_and_delay_provenance_are_deterministic():
    resolved = _green("2026-08-21T19:30:00-07:00")
    assert diary_cutoff_at(resolved) == _green("2026-08-21T21:30:00-07:00")
    assert format_delay(timedelta(0)) == "+00:00:00"
    assert format_delay(timedelta(hours=2, minutes=15, seconds=3)) == "+02:15:03"


def test_season_ids_are_sequential():
    assert next_season_id([]) == ("S01", 1)
    assert next_season_id(["S01", "S03", "not-a-season"]) == ("S04", 4)
