from pathlib import Path
import pytest
from govjobs.scrapers.generic_list import GenericListScraper
from govjobs.scrapers.pdf_notice import extract_smart_pdf_text_from_bytes

def test_aai_scraper():
    fixture_path = Path("tests/fixtures/aai.html")
    assert fixture_path.exists()
    content = fixture_path.read_text(encoding="utf-8")

    scraper = GenericListScraper(selectors={"row": "table tbody tr"})
    items = scraper.parse_list(content, base_url="https://www.aai.aero/en/careers/recruitment")

    assert len(items) > 10
    # Check Junior Executives GATE post exists
    je_posts = [it for it in items if "junior executives through gate" in it.title.lower()]
    assert len(je_posts) > 0
    post = je_posts[0]
    assert "976" in post.raw_text or "gate" in post.title.lower()
    assert post.url.startswith("https://")

def test_ssc_scraper():
    fixture_path = Path("tests/fixtures/ssc.html")
    assert fixture_path.exists()
    content = fixture_path.read_text(encoding="utf-8")

    scraper = GenericListScraper(selectors={"row": ".innerCard", "title": ".text"})
    items = scraper.parse_list(content, base_url="https://ssc.gov.in/home/notice-board")

    assert len(items) >= 5
    assert any("examination" in it.title.lower() or "translators" in it.title.lower() for it in items)

def test_powergrid_scraper():
    fixture_path = Path("tests/fixtures/powergrid.html")
    assert fixture_path.exists()
    content = fixture_path.read_text(encoding="utf-8")

    scraper = GenericListScraper()
    items = scraper.parse_list(content, base_url="https://www.powergrid.in/job-opportunities")

    assert len(items) > 5
    gate_items = [it for it in items if "gate" in it.title.lower() or "trainee" in it.title.lower()]
    assert len(gate_items) > 0
