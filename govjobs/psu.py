import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import yaml
from bs4 import BeautifulSoup
from rich.console import Console
from rich.table import Table

from govjobs.fetch import PoliteFetcher
from govjobs.registry import load_sources
from govjobs.store import JobStore
from govjobs.utils import fmt_date, IST

WIKIPEDIA_PSU_URL = "https://en.wikipedia.org/wiki/List_of_public_sector_undertakings_in_India"

def normalize_ratna_label(raw: Optional[str]) -> Tuple[str, bool]:
    """
    Normalise Wikipedia's inconsistent ratna labels.
    Returns (ratna_class, is_recognized).
    Valid classes: maharatna, navratna, miniratna_1, miniratna_2, none.
    """
    if not raw or not str(raw).strip():
        return "none", True
    
    s = str(raw).strip()
    if s in ["-", "–", "—", "None", "none", "N/A", "n/a"]:
        return "none", True

    clean = re.sub(r"\[.*?\]", "", s).strip()
    clean_lower = clean.lower()

    if re.search(r"\bmaharatna\b", clean_lower):
        return "maharatna", True

    if re.search(r"\bnavratna\b", clean_lower):
        return "navratna", True

    # Miniratna Category I (handles Roman I, digit 1, letter l)
    if re.search(r"mini\s*ratna.*(?:category\s*[-–—]?\s*(?:i\b|1\b|l\b)|cat\s*[-–—]?\s*(?:i\b|1\b|l\b))", clean_lower):
        return "miniratna_1", True

    # Miniratna Category II (handles Roman II, digit 2)
    if re.search(r"mini\s*ratna.*(?:category\s*[-–—]?\s*(?:ii\b|2\b)|cat\s*[-–—]?\s*(?:ii\b|2\b))", clean_lower):
        return "miniratna_2", True

    # Generic miniratna without category
    if "miniratna" in clean_lower or "mini ratna" in clean_lower:
        return "miniratna_1", True

    return "none", False

def _normalize_corp_name(name: str) -> str:
    """Normalize company name by stripping common suffixes like Limited, Corporation, etc."""
    s = name.lower()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"\b(corporation|limited|ltd|india|company|co)\b", "", s)
    s = re.sub(r"[^\w\s]", "", s)
    return " ".join(s.split())

def sync_psu_registry(
    wikipedia_url: str = WIKIPEDIA_PSU_URL,
    overrides_file: str = "psu_overrides.yaml",
    output_file: str = "psu_registry.yaml",
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Fetch Wikipedia PSU list, parse main table, normalize ratna labels,
    apply manual overrides from psu_overrides.yaml, and write psu_registry.yaml.
    Returns (psu_list, unrecognised_ratna_labels).
    """
    fetcher = PoliteFetcher()
    res = fetcher.fetch(wikipedia_url)
    if not res.ok or not res.content:
        raise RuntimeError(f"Failed to fetch Wikipedia PSU list from {wikipedia_url}: {res.error}")

    soup = BeautifulSoup(res.content, "html.parser")
    tables = soup.find_all("table", class_="wikitable")
    if not tables:
        raise RuntimeError("No wikitables found on Wikipedia page.")

    main_table = tables[0]
    psus: List[Dict[str, Any]] = []
    unrecognised_labels: List[str] = []

    for tr in main_table.find_all("tr")[1:]:
        tds = tr.find_all(["td", "th"])
        if len(tds) < 7:
            continue

        raw_name = tds[0].get_text(separator=" ", strip=True)
        raw_name = re.sub(r"\[.*?\]", "", raw_name).strip()
        if not raw_name:
            continue

        # Extract alias/acronym in parentheses
        aliases = []
        acronym_match = re.search(r"\((.*?)\)", raw_name)
        if acronym_match:
            acronym = acronym_match.group(1).strip()
            # Ignore parenthetical words that are not genuine acronyms (e.g. (India))
            stop_acronyms = {"india", "limited", "ltd", "company", "co", "corporation", "central", "state", "national"}
            if len(acronym) >= 2 and acronym.lower() not in stop_acronyms:
                aliases.append(acronym)
            clean_name = re.sub(r"\(.*?\)", "", raw_name).strip()
        else:
            clean_name = raw_name

        # Links in name td
        website = None
        for a in tds[0].find_all("a"):
            href = a.get("href", "")
            if href.startswith("http://") or href.startswith("https://"):
                website = href
                break

        ministry = re.sub(r"\[.*?\]", "", tds[2].get_text(strip=True)).strip()
        hq = re.sub(r"\[.*?\]", "", tds[3].get_text(strip=True)).strip()
        sector = re.sub(r"\[.*?\]", "", tds[4].get_text(strip=True)).strip()
        group = tds[5].get_text(strip=True).lower()
        ratna_raw = tds[6].get_text(strip=True)

        ratna_class, is_rec = normalize_ratna_label(ratna_raw)
        if not is_rec and ratna_raw:
            unrecognised_labels.append(f"{clean_name}: '{ratna_raw}'")

        # Operating status
        if "under construction" in group:
            operating_status = "under_construction"
        elif "dormant" in group:
            operating_status = "dormant"
        else:
            operating_status = "active"

        psu_record = {
            "name": clean_name,
            "aliases": aliases,
            "ratna_class": ratna_class,
            "schedule": None,
            "ministry": ministry,
            "sector": sector,
            "hq": hq,
            "website": website,
            "careers_url": None,
            "uses_gate": None,
            "operating_status": operating_status,
            "verified": False,
            "ratna_source_url": None,
            "verified_on": None,
        }
        psus.append(psu_record)

    # Apply manual overrides from psu_overrides.yaml
    overrides_p = Path(overrides_file)
    if overrides_p.exists():
        overrides_data = yaml.safe_load(overrides_p.read_text(encoding="utf-8")) or []
        for ov in overrides_data:
            ov_name = ov.get("name", "").strip().lower()
            ov_norm = _normalize_corp_name(ov_name)
            ov_aliases = [a.lower() for a in ov.get("aliases", [])]

            matched = False
            # 1. First pass: exact name or normalized name match
            for p in psus:
                p_name = p["name"].strip().lower()
                p_norm = _normalize_corp_name(p_name)
                if p_name == ov_name or (len(ov_norm) >= 4 and p_norm == ov_norm):
                    p["name"] = ov.get("name")
                    for k, v in ov.items():
                        if k == "aliases":
                            combined = list(dict.fromkeys(p.get("aliases", []) + v))
                            p["aliases"] = combined
                        elif v is not None:
                            p[k] = v
                    matched = True
                    break

            # 2. Second pass: alias match only if name didn't match
            if not matched:
                for p in psus:
                    p_name = p["name"].strip().lower()
                    p_aliases = [a.lower() for a in p.get("aliases", [])]
                    if any(a in ov_aliases for a in p_aliases) or any(a == p_name for a in ov_aliases):
                        p["name"] = ov.get("name")
                        for k, v in ov.items():
                            if k == "aliases":
                                combined = list(dict.fromkeys(p.get("aliases", []) + v))
                                p["aliases"] = combined
                            elif v is not None:
                                p[k] = v
                        matched = True
                        break

            if not matched:
                # Add missing PSU
                new_entry = {
                    "name": ov.get("name"),
                    "aliases": ov.get("aliases", []),
                    "ratna_class": ov.get("ratna_class", "none"),
                    "schedule": ov.get("schedule"),
                    "ministry": ov.get("ministry", ""),
                    "sector": ov.get("sector", ""),
                    "hq": ov.get("hq", ""),
                    "website": ov.get("website"),
                    "careers_url": ov.get("careers_url"),
                    "uses_gate": ov.get("uses_gate"),
                    "operating_status": ov.get("operating_status", "active"),
                    "verified": ov.get("verified", False),
                    "ratna_source_url": ov.get("ratna_source_url"),
                    "verified_on": ov.get("verified_on"),
                }
                psus.append(new_entry)

    # Sort: maharatna -> navratna -> miniratna_1 -> miniratna_2 -> none, then alphabetical
    rank = {"maharatna": 1, "navratna": 2, "miniratna_1": 3, "miniratna_2": 4, "none": 5}
    psus.sort(key=lambda x: (rank.get(x["ratna_class"], 99), x["name"].lower()))

    out_p = Path(output_file)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(yaml.safe_dump(psus, sort_keys=False, allow_unicode=True), encoding="utf-8")

    return psus, unrecognised_labels

_psu_cache: Optional[List[Dict[str, Any]]] = None

def load_psu_registry(path: str = "psu_registry.yaml") -> List[Dict[str, Any]]:
    global _psu_cache
    if _psu_cache is not None:
        return _psu_cache
    p = Path(path)
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or []
    _psu_cache = data
    return data

def find_psu_match(org_name: str, registry: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """
    Match an organization name against the PSU registry names and aliases.
    Uses case-insensitive exact, substring, or acronym matching.
    """
    if not org_name or not str(org_name).strip():
        return None
    if registry is None:
        registry = load_psu_registry()

    org_clean = org_name.strip().lower()
    org_tokens = set(re.findall(r"\w+", org_clean))

    # 1. Exact match on alias or full name
    for p in registry:
        p_name = p["name"].strip().lower()
        if p_name == org_clean:
            return p
        for a in p.get("aliases", []):
            if a.strip().lower() == org_clean:
                return p

    # 2. Token or substring match on alias (e.g. "BHEL" or "Cochin Shipyard")
    for p in registry:
        for a in p.get("aliases", []):
            a_clean = a.strip().lower()
            if not a_clean:
                continue
            if a_clean in org_tokens or (len(a_clean) >= 4 and a_clean in org_clean):
                return p

    # 3. Normalized name substring match
    org_norm = _normalize_corp_name(org_clean)
    for p in registry:
        p_name = p["name"].strip().lower()
        if len(p_name) > 6 and (p_name in org_clean or org_clean in p_name):
            return p
        p_norm = _normalize_corp_name(p["name"])
        if len(p_norm) >= 4 and (p_norm in org_norm or org_norm in p_norm):
            return p

    return None

def render_psu_coverage_table(console: Console, sources_file: str = "sources.yaml", registry_file: str = "psu_registry.yaml"):
    """
    Render PSU coverage view:
    One row per PSU: name, ratna class, careers URL found (yes/no), source enabled and healthy,
    jobs found, last job end date (DD/MM/YYYY). Sorted Maharatna first.
    Totals at the end: Maharatna X of Y covered, etc.
    """
    psus = load_psu_registry(registry_file)
    if not psus:
        console.print("[yellow]psu_registry.yaml is empty or missing. Run 'jobs psu-sync' first.[/yellow]")
        return

    sources = load_sources(sources_file)
    store = JobStore()
    all_jobs = store.get_all_jobs()

    # Map sources by name / url
    enabled_sources = {s.name.lower(): s for s in sources if s.enabled}

    table = Table(title="Central Public Sector Undertakings (PSU) Coverage Status", show_header=True)
    table.add_column("PSU Name", style="bold", width=32)
    table.add_column("Ratna Class", width=14)
    table.add_column("Careers URL", width=12)
    table.add_column("Source Status", width=16)
    table.add_column("Jobs", justify="right", width=6)
    table.add_column("Last End Date", style="yellow", width=13)

    counts = {
        "maharatna": {"total": 0, "covered": 0},
        "navratna": {"total": 0, "covered": 0},
        "miniratna_1": {"total": 0, "covered": 0},
        "miniratna_2": {"total": 0, "covered": 0},
        "none": {"total": 0, "covered": 0},
    }

    # Only show Ratna companies (maharatna, navratna, miniratna_1, miniratna_2) in detailed table
    ratna_psus = [p for p in psus if p["ratna_class"] != "none"]

    for p in ratna_psus:
        r_cls = p["ratna_class"]
        counts[r_cls]["total"] += 1

        # Check careers URL
        has_careers = bool(p.get("careers_url"))
        careers_str = "[green]Yes[/green]" if has_careers else "[red]No[/red]"

        # Check if source exists and is healthy
        p_name = p["name"].lower()
        aliases = [a.lower() for a in p.get("aliases", [])]

        src_match = None
        for s_name, s in enabled_sources.items():
            if s_name in p_name or p_name in s_name or any(a in s_name for a in aliases):
                src_match = s
                break

        if src_match:
            health = store.get_source_health(src_match.name)
            if health["failed_twice"] or health["zero_items_twice"]:
                src_status = "[bold red]Unhealthy[/bold red]"
            else:
                src_status = "[green]Enabled & OK[/green]"
            counts[r_cls]["covered"] += 1
        elif has_careers:
            src_status = "[yellow]Careers Known[/yellow]"
            counts[r_cls]["covered"] += 1
        else:
            src_status = "[dim]Missing[/dim]"

        # Jobs count and last end date
        matched_jobs = []
        for j in all_jobs:
            if j.psu_name and j.psu_name.lower() == p_name:
                matched_jobs.append(j)
            elif p_name in j.org.lower() or any(a in j.org.lower() for a in aliases):
                matched_jobs.append(j)

        num_jobs = len(matched_jobs)
        last_end = "-"
        if matched_jobs:
            valid_dates = [j.end_date for j in matched_jobs if j.end_date]
            if valid_dates:
                last_end = fmt_date(sorted(valid_dates)[-1])

        r_badge = {
            "maharatna": "[bold cyan]Maharatna[/bold cyan]",
            "navratna": "[bold green]Navratna[/bold green]",
            "miniratna_1": "[bold yellow]Miniratna-I[/bold yellow]",
            "miniratna_2": "[dim]Miniratna-II[/dim]",
        }.get(r_cls, r_cls)

        table.add_row(
            p["name"][:30],
            r_badge,
            careers_str,
            src_status,
            str(num_jobs),
            last_end
        )

    console.print(table)

    # Print summary totals
    console.print("\n[bold]PSU Coverage Summary:[/bold]")
    for r_cls, label in [
        ("maharatna", "Maharatna"),
        ("navratna", "Navratna"),
        ("miniratna_1", "Miniratna Category-I"),
        ("miniratna_2", "Miniratna Category-II"),
    ]:
        tot = counts[r_cls]["total"]
        cov = counts[r_cls]["covered"]
        pct = (cov / tot * 100) if tot > 0 else 0
        console.print(f"  • [bold]{label}:[/bold] {cov} of {tot} covered ({pct:.1f}%)")
    console.print("")

    # Section: Tips that matched a PSU with no registered source
    try:
        from govjobs.tipoff import get_all_tips
        tips = get_all_tips(status="new")
        missing_psu_tips = []
        for t in tips:
            psu_name = t.get("matched_psu")
            if psu_name:
                has_src = any(psu_name.lower() in s.name.lower() for s in sources if s.enabled)
                if not has_src:
                    missing_psu_tips.append(t)

        if missing_psu_tips:
            console.print("[bold yellow]Tips that matched a PSU with no registered source:[/bold yellow]")
            tip_table = Table(show_header=True)
            tip_table.add_column("Tip ID", style="dim", width=12)
            tip_table.add_column("Matched PSU", style="bold cyan", width=28)
            tip_table.add_column("Headline", width=40)
            tip_table.add_column("Tip Site", width=18)
            for t in missing_psu_tips[:10]:
                tip_table.add_row(t["id"][:10], t.get("matched_psu", "-"), t["title"][:38], t.get("tip_site", "-"))
            console.print(tip_table)
            console.print("[dim]Use 'jobs tips' and 'jobs tip-resolve <id> --url <official>' to add official source.[/dim]\n")
    except Exception:
        pass
