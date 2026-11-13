from pathlib import Path
import pytest
from govjobs.classify import classify_notice
from govjobs.scrapers.generic_list import GenericListScraper

def test_classify_ssc_fixture():
    fixture_path = Path("tests/fixtures/ssc.html")
    assert fixture_path.exists()
    content = fixture_path.read_text(encoding="utf-8")
    scraper = GenericListScraper(selectors={"row": ".innerCard", "title": ".text"})
    items = scraper.parse_list(content, base_url="https://ssc.gov.in/home/notice-board")

    results = [classify_notice("SSC", it.title, it.raw_text) for it in items]
    
    # Verify admit card is skipped
    admit_card_decisions = [r for r, it in zip(results, items) if "admit card" in it.title.lower()]
    assert len(admit_card_decisions) > 0
    assert all(r.decision == "skip" for r in admit_card_decisions)

    # Verify answer key / results are skipped
    key_decisions = [r for r, it in zip(results, items) if "answer key" in it.title.lower()]
    assert len(key_decisions) > 0
    assert all(r.decision == "skip" for r in key_decisions)

    # Verify recruitment / engagement is kept
    eng_decisions = [r for r, it in zip(results, items) if "engagement" in it.title.lower()]
    assert len(eng_decisions) > 0
    assert all(r.decision == "task" for r in eng_decisions)

def test_classify_drdo_rac_fixture():
    fixture_path = Path("tests/fixtures/drdo_rac.html")
    assert fixture_path.exists()
    content = fixture_path.read_text(encoding="utf-8")
    scraper = GenericListScraper(selectors={"row": "table tr, .advt-list li"})
    items = scraper.parse_list(content, base_url="https://rac.gov.in/")

    results = [classify_notice("DRDO RAC", it.title, it.raw_text) for it in items]

    # Verify # Status header rows are skipped
    hash_decisions = [r for r, it in zip(results, items) if it.title.strip().startswith("#")]
    assert len(hash_decisions) > 0
    assert all(r.decision == "skip" for r in hash_decisions)

    # Verify results and cutoffs are skipped
    result_decisions = [r for r, it in zip(results, items) if "result" in it.title.lower() or "cutoff" in it.title.lower()]
    assert len(result_decisions) > 0
    assert all(r.decision == "skip" for r in result_decisions)

    # Verify real vacancy notices are kept
    recruitment_decisions = [r for r, it in zip(results, items) if "vacancies" in it.title.lower() or "advt" in it.title.lower()]
    assert len(recruitment_decisions) > 0
    assert any(r.decision == "task" for r in recruitment_decisions)

def test_classify_powergrid_fixture():
    fixture_path = Path("tests/fixtures/powergrid.html")
    assert fixture_path.exists()
    content = fixture_path.read_text(encoding="utf-8")
    scraper = GenericListScraper()
    items = scraper.parse_list(content, base_url="https://www.powergrid.in/job-opportunities")

    results = [classify_notice("POWERGRID", it.title, it.raw_text) for it in items]

    # Real advertisements are kept
    trainee_decisions = [r for r, it in zip(results, items) if "engineer trainee" in it.title.lower()]
    assert len(trainee_decisions) > 0
    assert any(r.decision == "task" for r in trainee_decisions)

def test_classify_cochin_shipyard_fixture():
    fixture_path = Path("tests/fixtures/cochin_shipyard.html")
    assert fixture_path.exists()
    content = fixture_path.read_text(encoding="utf-8")
    scraper = GenericListScraper(selectors={"row": "table tr, .career-content"})
    items = scraper.parse_list(content, base_url="https://cochinshipyard.in/career")

    results = [classify_notice("CSL", it.title, it.raw_text) for it in items]

    # Menu items and table headers are skipped
    menu_decisions = [r for r, it in zip(results, items) if it.title.strip().lower() in [
        "current job openings", "select location", "name of the post", "faqs"
    ]]
    assert len(menu_decisions) > 0
    assert all(r.decision == "skip" for r in menu_decisions)

    # Vacancy notices are kept
    vacancy_decisions = [r for r, it in zip(results, items) if "vacancy notification" in it.title.lower()]
    assert len(vacancy_decisions) > 0
    assert any(r.decision == "task" for r in vacancy_decisions)

def test_classify_corrigendum_and_updates():
    res1 = classify_notice("UPSC", "Corrigendum to Advt No. 12/2026 - Engineer Posts")
    assert res1.decision == "task"
    assert res1.kind == "update"

    res2 = classify_notice("NTPC", "Extension of Last Date for Submission of Applications for ET-2026")
    assert res2.decision == "task"
    assert res2.kind == "update"

    res3 = classify_notice("BHEL", "Revised dates and addendum for Executive Engineer Advt")
    assert res3.decision == "task"
    assert res3.kind == "update"
