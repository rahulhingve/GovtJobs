import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import pytest
from typer.testing import CliRunner
from govjobs.cli import app
from govjobs.store import JobStore
from govjobs.utils import IST

runner = CliRunner()

def test_record_and_get_source_run(tmp_path):
    db_file = tmp_path / "test.db"
    store = JobStore(db_path=str(db_file))

    run_at_1 = datetime.now(IST).isoformat()
    row_id = store.record_source_run(
        source_name="Test Source",
        run_at=run_at_1,
        fetch_ok=True,
        http_status=200,
        used_playwright=False,
        items_parsed=15,
        items_classified_job=3,
        tasks_created=2,
        error=None
    )
    assert row_id > 0

    runs = store.get_latest_source_runs("Test Source", limit=1)
    assert len(runs) == 1
    assert runs[0]["source_name"] == "Test Source"
    assert runs[0]["items_parsed"] == 15
    assert runs[0]["tasks_created"] == 2
    assert runs[0]["fetch_ok"] == 1

def test_source_health_flagging(tmp_path):
    db_file = tmp_path / "test.db"
    store = JobStore(db_path=str(db_file))

    # 1. Healthy source
    store.record_source_run("Healthy", datetime.now(IST).isoformat(), True, 200, False, 10, 2, 1, None)
    h_stat = store.get_source_health("Healthy")
    assert not h_stat["failed_twice"]
    assert not h_stat["zero_items_twice"]
    assert not h_stat["selectors_matched_nothing"]

    # 2. Selectors matched nothing (0 parsed when fetch_ok)
    store.record_source_run("ZeroParsed", datetime.now(IST).isoformat(), True, 200, False, 0, 0, 0, None)
    zp_stat = store.get_source_health("ZeroParsed")
    assert zp_stat["selectors_matched_nothing"]
    assert not zp_stat["zero_items_twice"]  # Only 1 run so far

    # 3. Zero items twice in a row
    store.record_source_run("ZeroParsed", datetime.now(IST).isoformat(), True, 200, False, 0, 0, 0, None)
    zp_stat2 = store.get_source_health("ZeroParsed")
    assert zp_stat2["zero_items_twice"]
    assert zp_stat2["selectors_matched_nothing"]

    # 4. Failed twice in a row
    store.record_source_run("Broken", (datetime.now(IST) - timedelta(hours=1)).isoformat(), False, 500, False, 0, 0, 0, "Server Error")
    store.record_source_run("Broken", datetime.now(IST).isoformat(), False, 500, False, 0, 0, 0, "Server Error")
    br_stat = store.get_source_health("Broken")
    assert br_stat["failed_twice"]
    assert not br_stat["selectors_matched_nothing"]

def test_cli_sources_command():
    result = runner.invoke(app, ["sources"])
    assert result.exit_code == 0
    assert "Sources Registry & Pipeline Status" in result.stdout
    assert "Registered Recruitment Sources Health" in result.stdout
