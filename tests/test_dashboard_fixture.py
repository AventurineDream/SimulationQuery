from pathlib import Path

import pytest

from improv_troupe.application import read_service_status

from tests.support import build_s02_dashboard_fixture


def test_s02_fixture_covers_dashboard_rehearsal_states_deterministically(tmp_path):
    first = build_s02_dashboard_fixture(tmp_path / "first")
    second = build_s02_dashboard_fixture(tmp_path / "second")
    try:
        status = read_service_status(first.database, paths=first.paths, now=first.now)
        season = status["seasons"][0]
        assert season["season_id"] == "S02"
        assert season["status"] == "RECOVERY_REQUIRED"
        assert season["wellness_policy"] == "MANUAL_REVIEW"
        assert season["run_counts"] == {
            "COMPLETED": 1,
            "QUEUED": 1,
            "RECOVERY_REQUIRED": 1,
        }
        assert season["diary_counts"] == {
            "LATE": 1,
            "MISSING": 1,
            "PRIVATE": 1,
            "WRITTEN": 1,
        }
        assert status["integrity"] == "ok"
        assert status["notifications"] == {"unread": 1}
        assert len(status["recoveries"]) == 1
        assert status["recoveries"][0]["run_id"] == "S02-run-02"
        assert status["publications"][0]["status"] == "PRIVATE"

        day = first.database.connection.execute(
            "SELECT closed FROM days WHERE season_id = 'S02' AND day_number = 1"
        ).fetchone()
        assert day["closed"] == 1
        failed = first.database.connection.execute(
            "SELECT status, error_type, output_path FROM model_calls "
            "WHERE call_id = 'S02-run-02:tavi:r1:a1'"
        ).fetchone()
        assert (failed["status"], failed["error_type"]) == (
            "RETRYABLE_FAILURE",
            "SyntheticTimeout",
        )
        assert Path(failed["output_path"]).is_relative_to(first.paths.roots.private)

        query = (
            "SELECT run_id, status, turn_count, completion_reason FROM runs "
            "ORDER BY run_id"
        )
        assert [tuple(row) for row in first.database.connection.execute(query)] == [
            tuple(row) for row in second.database.connection.execute(query)
        ]
    finally:
        first.database.close()
        second.database.close()


@pytest.mark.parametrize(
    "root",
    [Path("/var/lib/improv-troupe"), Path("/var/lib"), Path("/")],
)
def test_s02_fixture_rejects_any_root_that_can_resolve_to_production(root):
    with pytest.raises(ValueError, match="production data root"):
        build_s02_dashboard_fixture(root)
