import json
import csv
from datetime import date
from pathlib import Path
import pytest

from govjobs.models import Job, Level, QualificationType, EmploymentType, generate_job_id
from govjobs.store import JobStore
from govjobs.render import export_csv, export_html

@pytest.fixture
def sample_jobs():
    today = date(2026, 11, 13)
    active_job = Job(
        id=generate_job_id("Active PSU", "01/2026", "Assistant Engineer"),
        org="Active PSU",
        post_title="Assistant Engineer",
        level=Level.PSU,
        sector="power",
        qualification_type=QualificationType.BTECH_REQUIRED,
        employment_type=EmploymentType.PERMANENT,
        start_date="2026-11-01",
        end_date="2026-11-20",  # Closes in 7 days -> active/expiring
        description="Active job posting description.",
        source_url="https://example.gov.in/active",
        first_seen="2026-11-01T00:00:00+05:30",
        last_seen="2026-11-01T00:00:00+05:30",
        content_hash="active_hash",
        confidence=1.0,
    )
    closed_job = Job(
        id=generate_job_id("Closed Central", "02/2026", "Junior Engineer"),
        org="Closed Central",
        post_title="Junior Engineer",
        level=Level.CENTRAL,
        sector="railways",
        qualification_type=QualificationType.BTECH_REQUIRED,
        employment_type=EmploymentType.PERMANENT,
        start_date="2026-05-01",
        end_date="2026-06-01",  # Ended months ago -> closed
        description="Closed job posting description.",
        source_url="https://example.gov.in/closed",
        first_seen="2026-05-01T00:00:00+05:30",
        last_seen="2026-05-01T00:00:00+05:30",
        content_hash="closed_hash",
        confidence=1.0,
    )
    return [active_job, closed_job]

def test_export_excludes_closed_by_default(tmp_path, sample_jobs):
    db_file = tmp_path / "test.db"
    store = JobStore(db_path=str(db_file))
    for j in sample_jobs:
        store.upsert_job(j)

    json_export = tmp_path / "jobs.json"
    archive_export = tmp_path / "archive.json"
    csv_export = tmp_path / "jobs.csv"
    html_export = tmp_path / "jobs.html"

    # Export JSON
    store.export_json(str(json_export), include_closed=False, archive_path=str(archive_export))
    exported_json = json.loads(json_export.read_text(encoding="utf-8"))
    archived_json = json.loads(archive_export.read_text(encoding="utf-8"))

    # Active file has only 1 job
    assert len(exported_json) == 1
    assert exported_json[0]["id"] == sample_jobs[0].id
    assert exported_json[0]["end_date_display"] == "20/11/2026"
    assert exported_json[0]["start_date_display"] == "01/11/2026"

    # Archive has closed job
    assert len(archived_json) == 1
    assert archived_json[0]["id"] == sample_jobs[1].id

    # Export CSV
    export_csv(sample_jobs, str(csv_export), include_closed=False)
    with open(csv_export, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
    assert len(reader) == 1
    assert reader[0]["id"] == sample_jobs[0].id
    assert reader[0]["end_date"] == "20/11/2026"

    # Export HTML
    export_html(sample_jobs, str(html_export), include_closed=False)
    html_content = html_export.read_text(encoding="utf-8")
    assert "Active PSU" in html_content
    assert "Closed Central" not in html_content
    assert "20/11/2026" in html_content
