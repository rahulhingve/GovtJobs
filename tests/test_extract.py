import json
from pathlib import Path
import pytest
from pydantic import ValidationError

from govjobs.models import Job, Branch, Level, QualificationType, EmploymentType, generate_job_id
from govjobs.extract import extract_rule_hints, map_branches_from_text, create_extraction_task, ingest_outbox
from govjobs.store import JobStore

def test_extract_rule_hints():
    text = """
    IMPORTANT DATES:
    Online application opens: 15/05/2026
    Closing date: 20.06.2026
    Candidates with B.Tech or B.E. in Civil Engineering are invited.
    Selection via GATE score.
    Total vacancies: 45 vacancies announced.
    """
    hints = extract_rule_hints(text)
    assert "15/05/2026" in hints["dates_found"]
    assert "20.06.2026" in hints["dates_found"]
    assert "2026-05-15" in hints["iso_dates"]
    assert "2026-06-20" in hints["iso_dates"]
    assert hints["gate_detected"] is True
    assert hints["vacancies_hint"] == 45
    assert len(hints["btech_keywords"]) > 0

def test_map_branches_from_text():
    text = "Candidate must have Computer Science & Engineering or Information Technology or Mech degree."
    branches = map_branches_from_text(text)
    assert Branch.CSE in branches
    assert Branch.IT in branches
    assert Branch.ME in branches

def test_ingest_validation(tmp_path):
    outbox = tmp_path / "outbox"
    done = tmp_path / "done"
    rejected = tmp_path / "rejected"
    outbox.mkdir()

    db_path = tmp_path / "test.db"
    store = JobStore(db_path=str(db_path))

    # 1. Valid job file
    valid_job_data = {
        "id": "valid_job_1",
        "org": "ISRO",
        "post_title": "Scientist/Engineer 'SC'",
        "notification_no": "ISRO:ICRB:01(BE):2026",
        "level": "central",
        "sector": "space",
        "qualification_type": "btech_required",
        "btech_eligible": True,
        "branches": ["CSE", "ECE"],
        "branches_raw": "BE/BTech in CSE or ECE",
        "gate_required": False,
        "additional_requirements": ["65% or 6.84 CGPA minimum"],
        "employment_type": "permanent",
        "vacancies": 30,
        "pay_level_or_scale": "Level 10",
        "start_date": "2026-04-01",
        "end_date": "2026-04-30",
        "description": "ISRO recruitment for Scientist Engineer SC in CSE and ECE branches.",
        "source_url": "https://www.isro.gov.in/Careers.html",
        "first_seen": "2026-04-01T10:00:00+05:30",
        "last_seen": "2026-04-01T10:00:00+05:30",
        "content_hash": "hash_valid",
        "confidence": 0.95,
        "needs_review": False
    }
    (outbox / "task_valid.json").write_text(json.dumps([valid_job_data]), encoding="utf-8")

    # 2. Invalid job: end_date < start_date
    invalid_job_data = valid_job_data.copy()
    invalid_job_data["id"] = "invalid_job_1"
    invalid_job_data["start_date"] = "2026-05-10"
    invalid_job_data["end_date"] = "2026-05-01"  # before start_date!
    (outbox / "task_invalid.json").write_text(json.dumps([invalid_job_data]), encoding="utf-8")

    valid_count, rejected_count, messages = ingest_outbox(
        outbox_dir=str(outbox),
        done_dir=str(done),
        rejected_dir=str(rejected),
        store=store
    )

    assert valid_count == 1
    assert rejected_count == 1
    assert (done / "task_valid.json").exists()
    assert (rejected / "task_invalid.json").exists()
    assert (rejected / "task_invalid.error.txt").exists()
    expected_id = generate_job_id("ISRO", "ISRO:ICRB:01(BE):2026", "Scientist/Engineer 'SC'")
    assert store.get_job(expected_id) is not None
