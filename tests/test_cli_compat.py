import subprocess
import sys
from pathlib import Path


EXAMPLE = Path(__file__).parent.parent / "examples" / "the_last_train.plan.json"


def test_production_plan_v1_dry_run_still_exports_markdown(tmp_path):
    output = tmp_path / "compat.script.md"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "improv_troupe.cli",
            "run",
            str(EXAMPLE),
            "--dry-run",
            "-o",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "# The Last Train" in output.read_text(encoding="utf-8")


def test_service_cli_migrate_status_and_one_dry_run_poll(tmp_path):
    data_root = tmp_path / "service-data"
    migrate = subprocess.run(
        [
            sys.executable,
            "-m",
            "improv_troupe.cli",
            "migrate",
            "--data-root",
            str(data_root),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert migrate.returncode == 0, migrate.stderr + migrate.stdout
    assert '"integrity": "ok"' in migrate.stdout

    status = subprocess.run(
        [
            sys.executable,
            "-m",
            "improv_troupe.cli",
            "status",
            "--data-root",
            str(data_root),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert status.returncode == 0, status.stderr + status.stdout
    assert '"schema_version": 6' in status.stdout

    serve = subprocess.run(
        [
            sys.executable,
            "-m",
            "improv_troupe.cli",
            "serve",
            "--data-root",
            str(data_root),
            "--dry-run",
            "--once",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert serve.returncode == 0, serve.stderr + serve.stdout
    assert "service poll complete" in serve.stdout
