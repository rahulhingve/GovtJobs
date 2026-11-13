import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse
import yaml
from rich.console import Console
from rich.table import Table

from govjobs.fetch import PoliteFetcher
from govjobs.psu import find_psu_match, load_psu_registry
from govjobs.registry import load_sources
from govjobs.store import JobStore
from govjobs.utils import IST, fmt_datetime_ist

logger = logging.getLogger("govjobs.tipoff")

ENGINEERING_KEYWORDS = [
    "engineer", "engineering", "btech", "b.tech", "b.e", "be/btech",
    "gate", "scientist", "trainee", "apprentice", "technical officer",
    "executive trainee", "junior engineer", "assistant engineer"
]

def is_aggregator_domain(url: str, tipoff_sources_file: str = "tipoff_sources.yaml") -> bool:
    """Check if a URL belongs to a blocked aggregator domain."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        netloc = (parsed.netloc or "").lower()
        blocked = {"sarkariresult.com", "testbook.com", "indgovtjobs.in", "freejobalert.com"}
        p = Path(tipoff_sources_file)
        if p.exists():
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or []
            for item in data:
                if item.get("kind") == "aggregator":
                    d = (item.get("verified_domain") or item.get("domain", "")).lower()
                    if d:
                        blocked.add(d)
        for b in blocked:
            if b in netloc:
                return True
        return False
    except Exception:
        return False

def load_tipoff_sources(path: str = "tipoff_sources.yaml") -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    return yaml.safe_load(p.read_text(encoding="utf-8")) or []

def purge_old_tips(tips_dir: str = "data/tips", max_days: int = 30) -> int:
    """Delete tips discovered more than max_days ago."""
    p = Path(tips_dir)
    if not p.exists():
        return 0
    now = datetime.now(IST)
    purged = 0
    for tip_file in p.glob("*.json"):
        try:
            data = json.loads(tip_file.read_text(encoding="utf-8"))
            disc_at_str = data.get("discovered_at")
            if disc_at_str:
                dt = datetime.fromisoformat(disc_at_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=IST)
                if (now - dt).days > max_days:
                    tip_file.unlink()
                    purged += 1
        except Exception:
            pass
    return purged

def is_engineering_or_psu_recruitment(title: str, registry: Optional[List[Dict[str, Any]]] = None) -> Tuple[bool, Optional[str]]:
    """
    Check if headline relates to engineering or a known PSU.
    Returns (matches, matched_psu_name).
    """
    t_clean = title.lower()
    psu_match = find_psu_match(title, registry=registry)
    if psu_match:
        return True, psu_match["name"]

    for kw in ENGINEERING_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", t_clean):
            return True, None

    return False, None

def run_tipoff(
    tipoff_sources_file: str = "tipoff_sources.yaml",
    tips_dir: str = "data/tips",
    fetcher: Optional[PoliteFetcher] = None,
    fixture_content_map: Optional[Dict[str, str]] = None,
) -> Tuple[int, int, List[str]]:
    """
    Politely scrape tip-off sources, find engineering or PSU notices,
    and save new tips to data/tips/<tip_id>.json without storing aggregator text.
    """
    p_tips = Path(tips_dir)
    p_tips.mkdir(parents=True, exist_ok=True)
    purge_old_tips(tips_dir=tips_dir)

    sources = load_tipoff_sources(tipoff_sources_file)
    if fetcher is None:
        fetcher = PoliteFetcher()

    registry = load_psu_registry()
    now_iso = datetime.now(IST).isoformat()

    # Collect existing tips URLs and titles
    known_tip_urls = set()
    for tip_f in p_tips.glob("*.json"):
        try:
            d = json.loads(tip_f.read_text(encoding="utf-8"))
            if d.get("tip_url"):
                known_tip_urls.add(d["tip_url"])
        except Exception:
            pass

    tips_created = 0
    skipped_count = 0
    logs: List[str] = []

    from govjobs.scrapers.generic_list import GenericListScraper

    for s in sources:
        if not s.get("enabled", True):
            logs.append(f"Skipping disabled tip-off source: {s['name']}")
            continue

        site_name = s["name"]
        list_url = s["list_url"]
        selectors = s.get("selectors")

        content = None
        if fixture_content_map is not None:
            if site_name not in fixture_content_map:
                continue
            content = fixture_content_map[site_name]
        else:
            res = fetcher.fetch(list_url)
            if not res.ok:
                logs.append(f"Failed to fetch {site_name} ({list_url}): {res.error}")
                continue
            content = res.content

        if not content:
            continue

        scraper = GenericListScraper(selectors=selectors)
        items = scraper.parse_list(content, base_url=list_url)

        for item in items:
            title = item.title.strip()
            item_url = item.url or list_url
            if not title or len(title) < 8 or item_url in known_tip_urls:
                continue

            matches, matched_psu = is_engineering_or_psu_recruitment(title, registry=registry)
            if not matches:
                skipped_count += 1
                continue

            tip_id = hashlib.sha256(f"{site_name}|{title}|{item_url}".encode("utf-8")).hexdigest()[:16]
            tip_payload = {
                "id": tip_id,
                "title": title,
                "tip_site": site_name,
                "tip_url": item_url,
                "matched_psu": matched_psu,
                "status": "new",
                "discovered_at": now_iso,
                "official_url": None,
            }

            tip_file = p_tips / f"{tip_id}.json"
            tip_file.write_text(json.dumps(tip_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            known_tip_urls.add(item_url)
            tips_created += 1
            logs.append(f"Created tip {tip_id}: '{title[:50]}' (PSU: {matched_psu or 'General Eng'})")

    return tips_created, skipped_count, logs

def get_all_tips(tips_dir: str = "data/tips", status: Optional[str] = None) -> List[Dict[str, Any]]:
    p = Path(tips_dir)
    if not p.exists():
        return []
    tips = []
    for f in p.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if status is None or d.get("status") == status:
                tips.append(d)
        except Exception:
            pass
    tips.sort(key=lambda x: x.get("discovered_at", ""), reverse=True)
    return tips

def resolve_tip(tip_id: str, official_url: Optional[str] = None, drop: bool = False, tips_dir: str = "data/tips") -> Tuple[bool, str]:
    """
    Resolve a tip:
    - If official_url is given: validates domain is not aggregator, creates task, marks resolved.
    - If drop is True: marks tip as dropped.
    """
    p = Path(tips_dir) / f"{tip_id}.json"
    if not p.exists():
        return False, f"Tip {tip_id} not found in {tips_dir}"

    tip = json.loads(p.read_text(encoding="utf-8"))

    if drop:
        tip["status"] = "dropped"
        p.write_text(json.dumps(tip, indent=2, ensure_ascii=False), encoding="utf-8")
        return True, f"Tip {tip_id} marked as dropped."

    if not official_url:
        return False, "Must provide --url <official_url> or --drop"

    clean_url = official_url.strip()
    if is_aggregator_domain(clean_url):
        return False, f"Rejected: '{clean_url}' is on a blocked aggregator domain. Must be official recruiter domain (.gov.in, .nic.in, or PSU portal)."

    # Create extraction task from official URL
    from govjobs.extract import create_extraction_task
    from govjobs.scrapers.pdf_notice import extract_pdf_from_url

    fetcher = PoliteFetcher()
    if clean_url.lower().endswith(".pdf"):
        text = extract_pdf_from_url(clean_url)
        notice_url = clean_url
    else:
        res = fetcher.fetch(clean_url)
        if not res.ok:
            return False, f"Failed to fetch official URL {clean_url}: {res.error}"
        text = res.content
        notice_url = None

    task_id, reason = create_extraction_task(
        source_name=tip.get("matched_psu") or "Tip-off Discovery",
        source_url=clean_url,
        notice_url=notice_url,
        notice_title=tip.get("title"),
        category="PSUs and CPSEs" if tip.get("matched_psu") else "Central exams and boards",
        text_content=text or tip.get("title", ""),
        org_level="psu" if tip.get("matched_psu") else "other",
        sector="engineering",
        include_old=True,
    )

    tip["status"] = "resolved"
    tip["official_url"] = clean_url
    p.write_text(json.dumps(tip, indent=2, ensure_ascii=False), encoding="utf-8")

    return True, f"Tip {tip_id} resolved! Created extraction task data/inbox/{task_id}.json."
