import json
import re
from datetime import date, timedelta
from pathlib import Path
import pytest
from bs4 import BeautifulSoup

from govjobs.models import Job, Level, QualificationType, EmploymentType, generate_job_id
from govjobs.render import export_html
from govjobs.utils import IST

def test_html_xss_escaping(tmp_path):
    malicious_job = Job(
        id=generate_job_id("Test Org", "01/2026", "Test Title"),
        org="Test <script>alert('org')</script>",
        post_title="Title <img src=x onerror=alert('xss')>",
        level=Level.CENTRAL,
        sector="general",
        qualification_type=QualificationType.BTECH_REQUIRED,
        employment_type=EmploymentType.PERMANENT,
        start_date="2026-11-01",
        end_date="2026-11-20",
        description="Malicious description <script>window.pwned=true;</script> with <b>tags</b>.",
        source_url="https://example.gov.in/job",
        first_seen="2026-11-01T00:00:00+05:30",
        last_seen="2026-11-01T00:00:00+05:30",
        content_hash="hash_xss",
    )

    out_file = tmp_path / "xss_test.html"
    export_html([malicious_job], str(out_file), include_closed=True)
    html_text = out_file.read_text(encoding="utf-8")

    # Raw script tags in JSON must be escaped as \u003cscript\u003e
    assert "<script>window.pwned=true;</script>" not in html_text
    assert "\\u003cscript\\u003e" in html_text
    assert "\\u003c/script\\u003e" in html_text

def test_html_ui_fixture_30_mixed_jobs(tmp_path):
    today = date(2026, 11, 13)
    jobs = []

    psu_classes = ["maharatna", "navratna", "miniratna_1", "miniratna_2", "none"]
    levels = [Level.PSU, Level.CENTRAL, Level.STATE, Level.DEFENCE]

    for i in range(30):
        # 0-9: Expiring (end_date within 1-7 days)
        # 10-19: Active (end_date in 15-40 days)
        # 20-24: Upcoming (start_date in future)
        # 25-27: Unverified (needs_review=True, end_date=None)
        # 28-29: Closed (end_date in past)
        if i < 10:
            s_date = (today - timedelta(days=20)).isoformat()
            e_date = (today + timedelta(days=(i % 7) + 1)).isoformat()
            review = False
        elif i < 20:
            s_date = (today - timedelta(days=10)).isoformat()
            e_date = (today + timedelta(days=20 + i)).isoformat()
            review = False
        elif i < 25:
            s_date = (today + timedelta(days=5 + i)).isoformat()
            e_date = (today + timedelta(days=35 + i)).isoformat()
            review = False
        elif i < 28:
            s_date = (today - timedelta(days=5)).isoformat()
            e_date = None
            review = True
        else:
            s_date = (today - timedelta(days=60)).isoformat()
            e_date = (today - timedelta(days=20)).isoformat()
            review = False

        j = Job(
            id=generate_job_id(f"Org_{i}", f"Advt_{i}", f"Post_{i}"),
            org=f"Organisation {i}",
            post_title=f"Engineer Grade {i}",
            level=levels[i % len(levels)],
            sector="engineering",
            psu_name=f"PSU {i}" if i % 2 == 0 else None,
            psu_class=psu_classes[i % len(psu_classes)],
            qualification_type=QualificationType.BTECH_REQUIRED,
            employment_type=EmploymentType.PERMANENT,
            gate_required=(i % 3 == 0),
            vacancies=10 + i * 2,
            start_date=s_date,
            end_date=e_date,
            description=f"Recruitment for Engineer Grade {i}.",
            source_url=f"https://recruiter{i}.gov.in/careers",
            notice_url=f"https://recruiter{i}.gov.in/notice.pdf" if i % 2 == 0 else None,
            first_seen="2026-11-01T00:00:00+05:30",
            last_seen="2026-11-01T00:00:00+05:30",
            content_hash=f"hash_{i}",
            needs_review=review,
            review_reason="Dates unverified" if review else None,
        )
        jobs.append(j)

    out_file = tmp_path / "mixed_jobs.html"
    export_html(jobs, str(out_file), include_closed=True)
    html_text = out_file.read_text(encoding="utf-8")

    soup = BeautifulSoup(html_text, "html.parser")

    # 1. Zero external network requests
    external_links = [l.get("href") for l in soup.find_all("link") if l.get("href") and l.get("href").startswith(("http://", "https://"))]
    external_scripts = [s.get("src") for s in soup.find_all("script") if s.get("src") and s.get("src").startswith(("http://", "https://"))]
    assert len(external_links) == 0, f"Found external links: {external_links}"
    assert len(external_scripts) == 0, f"Found external scripts: {external_scripts}"

    # 2. Embedded JSON data
    script_data = soup.find("script", id="jobs-data")
    assert script_data is not None
    loaded_data = json.loads(script_data.text)
    assert len(loaded_data) == 30

    # 3. Check tabs and controls exist
    assert soup.find("button", id="tab-expiring") is not None
    assert soup.find("button", id="tab-active") is not None
    assert soup.find("button", id="tab-upcoming") is not None
    assert soup.find("button", id="tab-unverified") is not None
    assert soup.find("button", id="tab-all") is not None
    assert soup.find("input", id="search-input") is not None
