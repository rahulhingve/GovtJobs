import json
from datetime import datetime, timedelta
from pathlib import Path
import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from govjobs.cli import app
from govjobs.models import Job, Level, QualificationType, EmploymentType
from govjobs.tipoff import (
    is_aggregator_domain,
    run_tipoff,
    purge_old_tips,
    resolve_tip,
    get_all_tips,
)
from govjobs.utils import IST

runner = CliRunner()

def test_aggregator_domain_detection():
    assert is_aggregator_domain("https://www.sarkariresult.com/2026/job.php")
    assert is_aggregator_domain("https://testbook.com/government-jobs")
    assert is_aggregator_domain("https://www.indgovtjobs.in/recruitment.html")
    assert is_aggregator_domain("https://freejobalert.com/central-jobs")

    # Official recruiter domains must NOT be treated as aggregators
    assert not is_aggregator_domain("https://careers.bhel.in/")
    assert not is_aggregator_domain("https://www.powergrid.in/job-opportunities")
    assert not is_aggregator_domain("https://upsc.gov.in/recruitment")
    assert not is_aggregator_domain("https://drdo.gov.in/")

def test_job_model_rejects_aggregator_source_url():
    valid_data = {
        "id": "test_job_hash_1",
        "org": "BHEL",
        "post_title": "Engineer Trainee",
        "level": Level.PSU,
        "sector": "power",
        "qualification_type": QualificationType.BTECH_REQUIRED,
        "btech_eligible": True,
        "branches": ["CE"],
        "employment_type": EmploymentType.PERMANENT,
        "description": "Engineer trainee recruitment at BHEL.",
        "source_url": "https://www.sarkariresult.com/2026/bhel.php",  # Aggregator!
        "first_seen": "2026-04-01T10:00:00+05:30",
        "last_seen": "2026-04-01T10:00:00+05:30",
        "content_hash": "hash_123",
    }
    with pytest.raises(ValidationError) as exc:
        Job(**valid_data)
    assert "source_url cannot be an aggregator URL" in str(exc.value)

def test_run_tipoff_fixtures(tmp_path):
    tips_dir = tmp_path / "tips"
    tips_dir.mkdir()

    sarkari_html = Path("tests/fixtures/tipoff_sarkariresult.html").read_text(encoding="utf-8")
    empnews_html = Path("tests/fixtures/tipoff_employmentnews.html").read_text(encoding="utf-8")

    fixture_map = {
        "Sarkari Result": sarkari_html,
        "Employment News": empnews_html,
    }

    created, skipped, logs = run_tipoff(
        tips_dir=str(tips_dir),
        fixture_content_map=fixture_map,
    )

    assert created >= 2
    assert skipped >= 2

    tips = get_all_tips(tips_dir=str(tips_dir))
    titles = [t["title"] for t in tips]

    # Engineering / PSU items kept
    assert any("BHEL" in t for t in titles)
    assert any("DRDO" in t for t in titles)

    # Non-engineering items dropped
    assert not any("UP Police" in t for t in titles)
    assert not any("SBI Clerk" in t for t in titles)

    # Aggregator text not stored
    for t in tips:
        assert "RAW" not in t
        assert "html" not in t

def test_tip_resolution_and_drop(tmp_path):
    tips_dir = tmp_path / "tips"
    tips_dir.mkdir()

    tip_payload = {
        "id": "tip_123456",
        "title": "BHEL Engineer Trainee 2026",
        "tip_site": "Sarkari Result",
        "tip_url": "https://www.sarkariresult.com/bhel.php",
        "matched_psu": "Bharat Heavy Electricals Limited",
        "status": "new",
        "discovered_at": datetime.now(IST).isoformat(),
        "official_url": None,
    }
    (tips_dir / "tip_123456.json").write_text(json.dumps(tip_payload), encoding="utf-8")

    # 1. Resolving with aggregator domain fails
    ok, msg = resolve_tip("tip_123456", official_url="https://testbook.com/bhel", tips_dir=str(tips_dir))
    assert not ok
    assert "blocked aggregator domain" in msg

    # 2. Dropping succeeds
    ok_drop, msg_drop = resolve_tip("tip_123456", drop=True, tips_dir=str(tips_dir))
    assert ok_drop
    d = json.loads((tips_dir / "tip_123456.json").read_text(encoding="utf-8"))
    assert d["status"] == "dropped"

def test_purge_old_tips(tmp_path):
    tips_dir = tmp_path / "tips"
    tips_dir.mkdir()

    now = datetime.now(IST)
    fresh_date = (now - timedelta(days=5)).isoformat()
    old_date = (now - timedelta(days=35)).isoformat()

    (tips_dir / "fresh.json").write_text(json.dumps({"id": "fresh", "discovered_at": fresh_date}))
    (tips_dir / "old.json").write_text(json.dumps({"id": "old", "discovered_at": old_date}))

    purged = purge_old_tips(tips_dir=str(tips_dir), max_days=30)
    assert purged == 1
    assert (tips_dir / "fresh.json").exists()
    assert not (tips_dir / "old.json").exists()
