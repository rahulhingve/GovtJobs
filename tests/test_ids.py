import difflib
import pytest
from govjobs.models import generate_job_id, normalize_key, Job, Level, QualificationType, EmploymentType
from govjobs.store import JobStore

def test_normalize_key():
    assert normalize_key("Power Grid Corp. (India) Ltd.") == "power grid corp india ltd"
    assert normalize_key("Executive   Trainee - 2026!") == "executive trainee 2026"

def test_stable_job_id():
    id1 = generate_job_id("NTPC Limited", "Advt 01/2026", "Assistant Manager")
    id2 = generate_job_id("ntpc limited", "advt 01/2026", "assistant manager")
    id3 = generate_job_id("NTPC Ltd", "Advt 01/2026", "Assistant Manager")
    
    assert id1 == id2
    assert id1 != id3

def test_deduplication_similarity(tmp_path):
    db_file = tmp_path / "test_jobs.db"
    store = JobStore(db_path=str(db_file))

    job1 = Job(
        id=generate_job_id("BARC", "01/2026", "Scientific Officer Technical"),
        org="BARC",
        post_title="Scientific Officer Technical",
        notification_no="01/2026",
        level=Level.CENTRAL,
        sector="atomic_energy",
        qualification_type=QualificationType.BTECH_REQUIRED,
        employment_type=EmploymentType.PERMANENT,
        description="Scientific officer post at BARC.",
        source_url="https://recruit.barc.gov.in",
        first_seen="2026-01-01T10:00:00+05:30",
        last_seen="2026-01-01T10:00:00+05:30",
        content_hash="hash1",
        confidence=1.0,
        start_date="2026-01-01",
        end_date="2026-02-01",
    )
    jid1, is_new1 = store.upsert_job(job1)
    assert is_new1 is True

    # Job2 has a minor typo / corrigendum in post title: "Scientific Officer (Technical)"
    # Similarity ratio will be >= 0.85
    ratio = difflib.SequenceMatcher(
        None,
        normalize_key("Scientific Officer Technical"),
        normalize_key("Scientific Officer (Technical)")
    ).ratio()
    assert ratio >= 0.85

    job2 = Job(
        id=generate_job_id("BARC", "01/2026", "Scientific Officer (Technical)"),
        org="BARC",
        post_title="Scientific Officer (Technical)",
        notification_no="01/2026",
        level=Level.CENTRAL,
        sector="atomic_energy",
        qualification_type=QualificationType.BTECH_REQUIRED,
        employment_type=EmploymentType.PERMANENT,
        description="Scientific officer post at BARC corrigendum.",
        source_url="https://recruit.barc.gov.in",
        first_seen="2026-01-05T10:00:00+05:30",
        last_seen="2026-01-05T10:00:00+05:30",
        content_hash="hash2",
        confidence=1.0,
        start_date="2026-01-01",
        end_date="2026-02-15",
    )
    jid2, is_new2 = store.upsert_job(job2)
    assert is_new2 is False
    assert jid2 == jid1

    # Verify updated record
    stored = store.get_job(jid1)
    assert stored is not None
    assert stored.end_date == "2026-02-15"
    assert stored.first_seen == "2026-01-01T10:00:00+05:30"
