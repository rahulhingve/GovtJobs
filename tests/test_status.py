from datetime import date, timedelta
import pytest
from govjobs.models import Job, Level, QualificationType, EmploymentType, generate_job_id
from govjobs.status import compute_job_status, JobStatus, job_sort_key

@pytest.fixture
def base_job():
    return Job(
        id=generate_job_id("Test Org", "Notice 1", "Civil Engineer"),
        org="Test Org",
        post_title="Civil Engineer",
        level=Level.CENTRAL,
        sector="civil",
        qualification_type=QualificationType.BTECH_REQUIRED,
        employment_type=EmploymentType.PERMANENT,
        description="Permanent civil engineering post in central government.",
        source_url="https://example.gov.in/jobs",
        first_seen="2026-01-01T00:00:00+05:30",
        last_seen="2026-01-01T00:00:00+05:30",
        content_hash="dummyhash",
        confidence=1.0,
        needs_review=False,
    )

def test_status_expiring(base_job):
    today = date(2026, 6, 1)
    # End date in 4 days -> expiring
    base_job.start_date = "2026-05-01"
    base_job.end_date = "2026-06-05"
    assert compute_job_status(base_job, today=today, expiring_days=7) == JobStatus.EXPIRING

def test_status_active(base_job):
    today = date(2026, 6, 1)
    # End date in 20 days -> active
    base_job.start_date = "2026-05-01"
    base_job.end_date = "2026-06-21"
    assert compute_job_status(base_job, today=today, expiring_days=7) == JobStatus.ACTIVE

def test_status_upcoming(base_job):
    today = date(2026, 6, 1)
    # Start date in the future
    base_job.start_date = "2026-06-15"
    base_job.end_date = "2026-07-15"
    assert compute_job_status(base_job, today=today, expiring_days=7) == JobStatus.UPCOMING

def test_status_closed(base_job):
    today = date(2026, 6, 1)
    # End date was yesterday
    base_job.start_date = "2026-05-01"
    base_job.end_date = "2026-05-31"
    assert compute_job_status(base_job, today=today, expiring_days=7) == JobStatus.CLOSED

def test_status_unknown_when_no_end_date(base_job):
    today = date(2026, 6, 1)
    base_job.start_date = "2026-05-01"
    base_job.end_date = None
    assert compute_job_status(base_job, today=today, expiring_days=7) == JobStatus.UNKNOWN

def test_sort_order(base_job):
    today = date(2026, 6, 1)
    
    j_expiring = base_job.model_copy(update={"id": "j_exp", "end_date": "2026-06-03", "start_date": "2026-05-01"})
    j_active = base_job.model_copy(update={"id": "j_act", "end_date": "2026-06-20", "start_date": "2026-05-01"})
    j_upcoming = base_job.model_copy(update={"id": "j_upc", "end_date": "2026-07-20", "start_date": "2026-06-10"})
    j_unknown = base_job.model_copy(update={"id": "j_unk", "end_date": None, "start_date": None})
    j_closed = base_job.model_copy(update={"id": "j_cls", "end_date": "2026-05-20", "start_date": "2026-05-01"})

    jobs_list = [j_closed, j_upcoming, j_unknown, j_expiring, j_active]
    sorted_jobs = sorted(jobs_list, key=lambda j: job_sort_key(j, today=today))

    # Order must be expiring -> active -> upcoming -> unknown -> closed
    assert [j.id for j in sorted_jobs] == ["j_exp", "j_act", "j_upc", "j_unk", "j_cls"]
