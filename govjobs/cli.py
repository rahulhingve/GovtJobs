import os
import sys
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List
import yaml
import typer
from rich.console import Console
from rich.table import Table
import httpx

from govjobs import __version__
from govjobs.models import Job, Level, Branch, QualificationType, EmploymentType
from govjobs.registry import load_sources, get_source_by_name
from govjobs.status import compute_job_status, JobStatus, job_sort_key
from govjobs.utils import get_ist_today, fmt_date, days_left, fmt_datetime_ist, IST
from govjobs.store import JobStore
from govjobs.extract import ingest_outbox

app = typer.Typer(help="GovJobs: Track Indian government permanent jobs open to BTech/BE graduates")
console = Console()

REQUIRED_DIRS = [
    "data",
    "data/cache",
    "data/inbox",
    "data/outbox",
    "data/done",
    "data/rejected",
    "tests/fixtures",
]

@app.command()
def doctor():
    """Check environment, network, playwright install, and folders."""
    console.print(f"[bold cyan]GovJobs Doctor (v{__version__})[/bold cyan]\n")
    table = Table(title="System & Environment Health", show_header=True, header_style="bold magenta")
    table.add_column("Component", style="cyan", width=25)
    table.add_column("Status", width=12)
    table.add_column("Details", style="dim")

    all_ok = True

    # 1. Python Version
    py_ver = sys.version_info
    if py_ver.major == 3 and py_ver.minor >= 11:
        table.add_row("Python Version", "[green]OK[/green]", f"{py_ver.major}.{py_ver.minor}.{py_ver.micro}")
    else:
        table.add_row("Python Version", "[red]FAIL[/red]", f"Requires >= 3.11, found {py_ver.major}.{py_ver.minor}")
        all_ok = False

    # 2. Required Directories
    missing_dirs = []
    for d in REQUIRED_DIRS:
        p = Path(d)
        if not p.exists():
            missing_dirs.append(d)
            p.mkdir(parents=True, exist_ok=True)
    if missing_dirs:
        table.add_row("Directories", "[yellow]FIXED[/yellow]", f"Created missing: {', '.join(missing_dirs)}")
    else:
        table.add_row("Directories", "[green]OK[/green]", "All data & test directories present")

    # 3. Registry (sources.yaml)
    try:
        sources = load_sources("sources.yaml")
        table.add_row("Sources Registry", "[green]OK[/green]", f"Loaded {len(sources)} sources from sources.yaml")
    except Exception as e:
        table.add_row("Sources Registry", "[red]FAIL[/red]", f"Error loading sources.yaml: {e}")
        all_ok = False

    # 4. Config (config.yaml)
    try:
        if Path("config.yaml").exists():
            with open("config.yaml", "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            table.add_row("Config File", "[green]OK[/green]", f"Loaded config.yaml (expiring_days={cfg.get('expiring_days', 7)})")
        else:
            table.add_row("Config File", "[yellow]WARN[/yellow]", "config.yaml not found (using defaults)")
    except Exception as e:
        table.add_row("Config File", "[red]FAIL[/red]", f"Error loading config.yaml: {e}")
        all_ok = False

    # 5. Playwright Chromium
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        table.add_row("Playwright Chromium", "[green]OK[/green]", "Headless Chromium browser functional")
    except Exception as e:
        table.add_row("Playwright Chromium", "[red]FAIL[/red]", f"Playwright error: {e}. Run 'playwright install chromium' to install.")
        all_ok = False

    # 6. SQLite DB
    try:
        store = JobStore()
        all_jobs = store.get_all_jobs()
        table.add_row("SQLite Database", "[green]OK[/green]", f"Connected to data/jobs.db ({len(all_jobs)} jobs stored)")
    except Exception as e:
        table.add_row("SQLite Database", "[red]FAIL[/red]", f"Database error: {e}")
        all_ok = False

    # 7. PSU Registry
    try:
        from govjobs.psu import load_psu_registry
        psus = load_psu_registry("psu_registry.yaml")
        if psus:
            table.add_row("PSU Registry", "[green]OK[/green]", f"Loaded {len(psus)} CPSEs from psu_registry.yaml")
        else:
            table.add_row("PSU Registry", "[yellow]WARN[/yellow]", "psu_registry.yaml not yet generated (run 'jobs psu-sync')")
    except Exception as e:
        table.add_row("PSU Registry", "[red]FAIL[/red]", f"Error loading psu_registry.yaml: {e}")
        all_ok = False

    # 8. Network Connectivity
    try:
        with httpx.Client(timeout=5.0, follow_redirects=True) as client:
            resp = client.get("https://1.1.1.1")
            if resp.status_code == 200:
                table.add_row("Network Connection", "[green]OK[/green]", "Internet connectivity verified")
            else:
                table.add_row("Network Connection", "[yellow]WARN[/yellow]", f"Status code: {resp.status_code}")
    except Exception as e:
        table.add_row("Network Connection", "[yellow]WARN[/yellow]", f"Network probe: {e}")

    console.print(table)
    if all_ok:
        console.print("\n[bold green]Doctor check PASSED: All systems operational.[/bold green]\n")
    else:
        console.print("\n[bold red]Doctor check FAILED: Please review issues above.[/bold red]\n")
        raise typer.Exit(code=1)

@app.command()
def sources():
    """List registry health, run metrics, plus inbox and outbox counts."""
    sources_list = load_sources("sources.yaml")
    store = JobStore()
    inbox_count = len(list(Path("data/inbox").glob("*.json"))) if Path("data/inbox").exists() else 0
    outbox_count = len(list(Path("data/outbox").glob("*.json"))) if Path("data/outbox").exists() else 0
    done_count = len(list(Path("data/done").glob("*.json"))) if Path("data/done").exists() else 0
    rejected_count = len(list(Path("data/rejected").glob("*.json"))) if Path("data/rejected").exists() else 0

    console.print(f"[bold cyan]Sources Registry & Pipeline Status[/bold cyan]")
    console.print(f"Inbox tasks pending: [bold yellow]{inbox_count}[/bold yellow] | Outbox ready: [bold green]{outbox_count}[/bold green] | Done: {done_count} | Rejected: {rejected_count}\n")

    table = Table(title="Registered Recruitment Sources Health", show_header=True)
    table.add_column("Name", style="bold", width=28)
    table.add_column("Category", style="dim", width=20)
    table.add_column("Last Run (IST)", width=18)
    table.add_column("Result", width=12)
    table.add_column("Items", justify="right", width=6)
    table.add_column("Last Task", justify="right", width=10)
    table.add_column("Flag", width=8)
    table.add_column("Last Error / Note", style="dim", width=26)

    for s in sources_list:
        health = store.get_source_health(s.name)
        last_run = health["last_run"]

        # Run time
        if last_run:
            run_time_str = fmt_datetime_ist(last_run["run_at"])
        else:
            run_time_str = "[dim]Never[/dim]"

        # Result
        if not s.enabled:
            result_str = "[dim]Disabled[/dim]"
        elif not last_run:
            result_str = "[dim]Never Run[/dim]"
        elif last_run["fetch_ok"] == 0:
            result_str = "[bold red]FAILED[/bold red]"
        elif last_run["items_parsed"] == 0:
            result_str = "[bold yellow]ZERO ITEMS[/bold yellow]"
        else:
            result_str = "[green]OK[/green]"

        # Items
        items_str = str(last_run["items_parsed"]) if last_run else "-"

        # Days since task
        dst = health["days_since_task"]
        if dst is not None:
            task_str = f"{dst}d ago"
        elif last_run and last_run["tasks_created"] > 0:
            task_str = "Today"
        else:
            task_str = "[dim]Never[/dim]"

        # Red Flags
        # Flag in red: failed twice in a row, or zero items twice in a row, or selectors matched nothing (0 items when fetch was OK)
        is_flagged = False
        flag_reason = []
        if health["failed_twice"]:
            is_flagged = True
            flag_reason.append("Failed 2x")
        if health["zero_items_twice"]:
            is_flagged = True
            flag_reason.append("0 items 2x")
        if health["selectors_matched_nothing"]:
            is_flagged = True
            flag_reason.append("0 parsed")

        if is_flagged and s.enabled:
            flag_str = "[bold red]RED[/bold red]"
        else:
            flag_str = "[green]OK[/green]" if (s.enabled and last_run and last_run["fetch_ok"] == 1 and last_run["items_parsed"] > 0) else "-"

        # Error / Note
        err_str = ""
        if last_run and last_run["error"]:
            err_str = str(last_run["error"])[:30]
        elif not s.enabled:
            err_str = "Disabled in sources.yaml"
        elif is_flagged:
            err_str = ", ".join(flag_reason)

        name_style = "[bold red]" + s.name[:27] + "[/bold red]" if (is_flagged and s.enabled) else s.name[:27]

        table.add_row(
            name_style,
            s.category[:19],
            run_time_str,
            result_str,
            items_str,
            task_str,
            flag_str,
            err_str,
        )

    console.print(table)

@app.command()
def ingest():
    """Validate and store the agent's outbox files."""
    valid, rejected, msgs = ingest_outbox()
    console.print(f"[bold]Ingest Results:[/bold] [green]{valid} stored[/green], [red]{rejected} rejected[/red]")
    for m in msgs:
        console.print(f"  • {m}")

@app.command(name="list")
def list_jobs(
    level: Optional[str] = typer.Option(None, "--level", "-l", help="Filter by level: central, state, ut, psu, defence, police"),
    state: Optional[str] = typer.Option(None, "--state", "-s", help="Filter by state name"),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="Filter by branch code (CSE, IT, ECE, EEE, ME, CE, etc.)"),
    sector: Optional[str] = typer.Option(None, "--sector", "-x", help="Filter by sector (power, oil, railways, etc.)"),
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status: expiring, active, upcoming"),
    gate_only: bool = typer.Option(False, "--gate-only", help="Show only jobs requiring GATE"),
    no_gate: bool = typer.Option(False, "--no-gate", help="Show only jobs NOT requiring GATE"),
    include_any_graduate: bool = typer.Option(False, "--include-any-graduate", help="Include jobs open to any graduate"),
    all_types: bool = typer.Option(False, "--all-types", help="Include contract, apprentice, trainee, deputation"),
    include_closed: bool = typer.Option(False, "--include-closed", help="Include closed notifications"),
    search: Optional[str] = typer.Option(None, "--search", help="Text search in org, post_title, description"),
    psu_class: Optional[str] = typer.Option(None, "--psu-class", help="Filter by PSU class: maharatna, navratna, miniratna, any"),
    psu: Optional[str] = typer.Option(None, "--psu", help="Filter by PSU name or alias (e.g. BHEL, NTPC, POWERGRID)"),
):
    """List jobs sorted expiring soon -> active -> upcoming."""
    store = JobStore()
    all_jobs = store.get_all_jobs()
    today = get_ist_today()

    filtered: List[Job] = []
    for j in all_jobs:
        # Default filter: employment_type == permanent unless --all-types
        if not all_types and j.employment_type != EmploymentType.PERMANENT:
            continue

        # Default filter: qualification_type in [btech_required, btech_or_equivalent] unless --include-any-graduate
        if not include_any_graduate and j.qualification_type == QualificationType.ANY_GRADUATE:
            continue

        # Level filter
        if level and j.level.value.lower() != level.lower():
            continue

        # State filter
        if state and (not j.state or state.lower() not in j.state.lower()):
            continue

        # Branch filter (case-insensitive, ALL matches any branch)
        if branch:
            b_norm = branch.strip().upper()
            j_branches = [b.value.upper() for b in j.branches]
            if "ALL" not in j_branches and b_norm not in j_branches:
                continue

        # Sector filter
        if sector and sector.lower() not in j.sector.lower():
            continue

        # GATE filters
        if gate_only and not j.gate_required:
            continue
        if no_gate and j.gate_required:
            continue

        # Status filter
        j_status = compute_job_status(j, today=today)
        if not include_closed and j_status == JobStatus.CLOSED:
            continue
        if status and j_status.value.lower() != status.lower():
            continue

        # Search query
        if search:
            q = search.lower()
            text_corpus = f"{j.org} {j.post_title} {j.description} {j.sector} {j.branches_raw or ''}".lower()
            if q not in text_corpus:
                continue

        # PSU class filter
        if psu_class:
            pc_norm = psu_class.strip().lower()
            j_cls = (j.psu_class or "").strip().lower()
            if pc_norm == "any":
                if not j_cls or j_cls == "none":
                    continue
            elif pc_norm == "miniratna":
                if j_cls not in ["miniratna_1", "miniratna_2"]:
                    continue
            else:
                if j_cls != pc_norm:
                    continue

        # PSU name filter
        if psu:
            p_query = psu.strip().lower()
            j_psu = (j.psu_name or "").lower()
            j_org = (j.org or "").lower()
            if p_query not in j_psu and p_query not in j_org:
                continue

        filtered.append(j)

    # Sort: expiring -> active -> upcoming -> unknown -> closed
    sorted_jobs = sorted(filtered, key=lambda x: job_sort_key(x, today=today))

    # Count how many closed jobs were hidden
    total_closed = sum(1 for j in all_jobs if compute_job_status(j, today=today) == JobStatus.CLOSED)

    if not sorted_jobs:
        console.print("[yellow]No matching jobs found.[/yellow]")
        if not include_closed and total_closed > 0:
            console.print(f"[dim]{total_closed} closed jobs hidden (use --include-closed)[/dim]")
        return

    table = Table(title=f"Government BTech Jobs ({len(sorted_jobs)} records)", show_header=True)
    table.add_column("Status", width=10)
    table.add_column("Organisation", style="bold cyan", width=25)
    table.add_column("Post Title", style="bold", width=30)
    table.add_column("Branches", style="green", width=15)
    table.add_column("Vacancies", width=10)
    table.add_column("Days Left", style="bold", width=11)
    table.add_column("End Date", style="yellow", width=12)
    table.add_column("Official Link", style="blue")

    for j in sorted_jobs:
        st = compute_job_status(j, today=today)
        st_color = {
            JobStatus.EXPIRING: "[red]Expiring[/red]",
            JobStatus.ACTIVE: "[green]Active[/green]",
            JobStatus.UPCOMING: "[blue]Upcoming[/blue]",
            JobStatus.UNKNOWN: "[yellow]Unverified[/yellow]",
            JobStatus.CLOSED: "[dim]Closed[/dim]",
        }.get(st, st.value)

        branch_str = ", ".join([b.value for b in j.branches]) if j.branches else "Unspecified"
        vac_str = str(j.vacancies) if j.vacancies is not None else "-"
        end_str = fmt_date(j.end_date)
        dl = days_left(j, today=today)
        if dl is not None:
            if dl < 0:
                dl_str = "[dim]Ended[/dim]"
            elif dl <= 3:
                dl_str = f"[bold red]{dl}d[/bold red]"
            elif dl <= 7:
                dl_str = f"[bold yellow]{dl}d[/bold yellow]"
            else:
                dl_str = f"[green]{dl}d[/green]"
        else:
            dl_str = "-"

        table.add_row(st_color, j.org[:25], j.post_title[:30], branch_str[:15], vac_str, dl_str, end_str, j.source_url)

    console.print(table)
    if not include_closed and total_closed > 0:
        console.print(f"\n[dim]{total_closed} closed job(s) hidden (use --include-closed)[/dim]")

@app.command()
def show(job_id: str):
    """Full detail + official links for a job record."""
    store = JobStore()
    job = store.get_job(job_id)
    if not job:
        console.print(f"[red]Job with ID '{job_id}' not found.[/red]")
        raise typer.Exit(code=1)

    today = get_ist_today()
    status = compute_job_status(job, today=today)
    dl = days_left(job, today=today)

    console.print(f"\n[bold cyan]=== {job.post_title} ===[/bold cyan]")
    console.print(f"[bold]Organisation:[/bold] {job.org} ({job.level.value.upper()})")
    if job.state:
        console.print(f"[bold]State:[/bold] {job.state}")
    console.print(f"[bold]Sector:[/bold] {job.sector}")
    if job.notification_no:
        console.print(f"[bold]Notification No:[/bold] {job.notification_no}")
    console.print(f"[bold]Status:[/bold] {status.value.upper()}" + (f" ({dl} days left)" if dl is not None and dl >= 0 else ""))
    console.print(f"[bold]Dates:[/bold] Start: {fmt_date(job.start_date)} | End: {fmt_date(job.end_date)}")
    console.print(f"[bold]Qualification Type:[/bold] {job.qualification_type.value} (BTech Eligible: {job.btech_eligible})")
    console.print(f"[bold]Branches:[/bold] {', '.join([b.value for b in job.branches]) or 'None'}")
    if job.branches_raw:
        console.print(f"[bold]Branches (as written):[/bold] {job.branches_raw}")
    console.print(f"[bold]GATE Required:[/bold] {'Yes' if job.gate_required else ('No' if job.gate_required is False else 'Not stated')}")
    if job.additional_requirements:
        console.print(f"[bold]Additional Requirements:[/bold] {', '.join(job.additional_requirements)}")
    console.print(f"[bold]Employment Type:[/bold] {job.employment_type.value}")
    console.print(f"[bold]Vacancies:[/bold] {job.vacancies or 'Not stated'}")
    if job.pay_level_or_scale:
        console.print(f"[bold]Pay Scale / Level:[/bold] {job.pay_level_or_scale}")
    console.print(f"\n[bold]Description:[/bold]\n{job.description}\n")
    console.print(f"[bold blue]Official Recruitment URL:[/bold blue] {job.source_url}")
    if job.notice_url:
        console.print(f"[bold blue]Official PDF Notice:[/bold blue] {job.notice_url}")
    console.print(f"[dim]Record ID: {job.id} | Confidence: {job.confidence:.2f} | First Seen: {job.first_seen} | Last Seen: {job.last_seen}[/dim]\n")

@app.command()
def review():
    """List needs_review items, allow confirm/edit fields."""
    store = JobStore()
    all_jobs = store.get_all_jobs()
    review_items = [j for j in all_jobs if j.needs_review]
    if not review_items:
        console.print("[green]No records currently marked for review.[/green]")
        return

    table = Table(title=f"Records Requiring Review ({len(review_items)})", show_header=True)
    table.add_column("ID", style="dim", width=12)
    table.add_column("Organisation", style="bold cyan")
    table.add_column("Post Title", style="bold")
    table.add_column("Confidence", width=10)
    table.add_column("Review Reason", style="yellow")

    for j in review_items:
        table.add_row(j.id, j.org[:25], j.post_title[:30], f"{j.confidence:.2f}", j.review_reason or "Unspecified")

    console.print(table)

@app.command(name="clean-inbox")
def clean_inbox_cmd():
    """Remove tasks from data/inbox that have already been processed."""
    from govjobs.extract import clean_inbox
    removed = clean_inbox()
    console.print(f"[green]Cleaned inbox:[/green] Removed {removed} processed task(s).")

@app.command()
def extract(limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Number of tasks to print")):
    """Print the next tasks for the agent, with instructions."""
    from govjobs.config import get_config
    cfg = get_config()
    batch_size = limit if limit is not None else cfg.extract_batch_size

    inbox_dir = Path("data/inbox")
    if not inbox_dir.exists():
        console.print("[yellow]Inbox directory data/inbox does not exist.[/yellow]")
        return

    # Filter out tasks already in outbox, done, done/tasks, rejected
    processed_stems = set()
    for folder in ["data/outbox", "data/done", "data/done/tasks", "data/rejected"]:
        fp = Path(folder)
        if fp.exists():
            for f in fp.glob("*.json"):
                processed_stems.add(f.stem)

    tasks = [f for f in inbox_dir.glob("*.json") if f.stem not in processed_stems]
    if not tasks:
        console.print("[green]No pending extraction tasks in data/inbox.[/green]")
        return

    # Load and sort tasks: updates first, then likely-active, then others
    task_objs = []
    for t_file in tasks:
        try:
            d = json.loads(t_file.read_text(encoding="utf-8"))
            task_objs.append((t_file, d))
        except Exception:
            task_objs.append((t_file, {}))

    def task_priority(item):
        _, data = item
        kind = data.get("kind", "new")
        likely_expired = data.get("likely_expired", False)
        # 1: updates, 2: active, 3: expired
        if kind == "update":
            return (1, data.get("created_at", ""))
        elif not likely_expired:
            return (2, data.get("created_at", ""))
        else:
            return (3, data.get("created_at", ""))

    task_objs.sort(key=task_priority)
    batch = task_objs[:batch_size]

    console.print("[bold yellow]>>> Read EXTRACTION.md before extracting. One task at a time. Output to data/outbox/<task_id>.json <<<\n[/bold yellow]")
    console.print(f"[bold cyan]Showing next {len(batch)} of {len(task_objs)} pending extraction task(s):[/bold cyan]\n")

    for t_file, data in batch:
        tid = data.get("task_id", t_file.stem)
        src = data.get("source_name", "Unknown")
        kind = data.get("kind", "new")
        hints = data.get("rule_hints", {})
        dates = hints.get("dates_found", [])
        branches = data.get("suggested_branches", [])
        is_exp = data.get("likely_expired", False)

        console.print(f"[bold magenta]┌── Task: {tid} | Source: {src} | Kind: {kind.upper()}" + (" | LIKELY EXPIRED" if is_exp else "") + "[/bold magenta]")
        notice_t = data.get("notice_title") or (data.get("notice_text", "").splitlines()[0].replace("TITLE:", "").strip() if data.get("notice_text") else "-")
        console.print(f"│ [cyan]Title:[/cyan] {notice_t}")
        console.print(f"│ [cyan]URL:[/cyan] {data.get('source_url', '-')}")
        if data.get("notice_url"):
            console.print(f"│ [cyan]PDF Notice:[/cyan] {data.get('notice_url')}")
        console.print(f"│ [cyan]Hints:[/cyan] Dates: {dates} | GATE: {hints.get('gate_detected')} | Branches: {branches}")
        if data.get("existing_record"):
            console.print(f"│ [yellow]Existing record found for update:[/yellow] {data['existing_record'].get('post_title')}")
        console.print("│ [dim]Text Preview:[/dim]")
        for line in (data.get("notice_text", "")[:400]).splitlines():
            console.print(f"│   {line}")
        console.print("└──\n")

@app.command()
def update(
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Fetch specific source name"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Fetch specific category"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Limit number of sources to update"),
    include_old: bool = typer.Option(False, "--include-old", help="Create tasks even for notices where all dates have passed"),
):
    """Fetch pages, parse notices, classify, and create extraction tasks."""
    from govjobs.fetch import PoliteFetcher
    from govjobs.extract import create_extraction_task
    from govjobs.scrapers.generic_list import GenericListScraper
    from govjobs.classify import classify_notice
    from govjobs.config import get_config
    import hashlib

    cfg = get_config()
    fetcher = PoliteFetcher()
    sources_list = load_sources("sources.yaml")
    store = JobStore()

    if source:
        sources_list = [s for s in sources_list if source.lower() in s.name.lower()]
    if category:
        sources_list = [s for s in sources_list if category.lower() in s.category.lower()]
    if limit:
        sources_list = sources_list[:limit]

    console.print(f"[bold cyan]Updating {len(sources_list)} source(s)...[/bold cyan]\n")
    tasks_created = 0
    classified_skipped = 0
    expired_skipped = 0

    # Collect known hashes from database, inbox, outbox, done, and rejected
    known_hashes = set()
    for j in store.get_all_jobs():
        if j.content_hash:
            known_hashes.add(j.content_hash)
    for folder in ["data/inbox", "data/outbox", "data/done", "data/done/tasks", "data/rejected"]:
        p = Path(folder)
        if p.exists():
            for f in p.glob("*.json"):
                known_hashes.add(f.stem)

    for s in sources_list:
        if not s.enabled:
            console.print(f"[dim]Skipping disabled source: {s.name}[/dim]")
            continue

        src_run_at = datetime.now(IST).isoformat()
        src_items_parsed = 0
        src_items_classified_job = 0
        src_tasks_created = 0

        console.print(f"Fetching [bold]{s.name}[/bold] ({s.list_url})...")
        force_pw = (s.type.value == "js_page")
        try:
            res = fetcher.fetch(s.list_url, verify_ssl=s.verify_ssl, force_playwright=force_pw)
        except Exception as e:
            console.print(f"  [red]Exception during fetch:[/red] {e}")
            store.record_source_run(
                source_name=s.name,
                run_at=src_run_at,
                fetch_ok=False,
                http_status=None,
                used_playwright=force_pw,
                items_parsed=0,
                items_classified_job=0,
                tasks_created=0,
                error=str(e),
            )
            continue

        if not res.ok:
            console.print(f"  [red]Failed to fetch:[/red] {res.error} (Status: {res.status_code})")
            store.record_source_run(
                source_name=s.name,
                run_at=src_run_at,
                fetch_ok=False,
                http_status=res.status_code,
                used_playwright=res.used_playwright,
                items_parsed=0,
                items_classified_job=0,
                tasks_created=0,
                error=res.error or f"HTTP {res.status_code}",
            )
            continue

        content = res.content
        if not content:
            console.print(f"  [yellow]Empty content received.[/yellow]")
            store.record_source_run(
                source_name=s.name,
                run_at=src_run_at,
                fetch_ok=True,
                http_status=res.status_code,
                used_playwright=res.used_playwright,
                items_parsed=0,
                items_classified_job=0,
                tasks_created=0,
                error="Empty content received",
            )
            continue

        # Parse notices
        scraper = GenericListScraper(selectors=s.selectors)
        items = scraper.parse_list(content, base_url=s.list_url)
        src_items_parsed = len(items)
        console.print(f"  Found [cyan]{len(items)}[/cyan] notice item(s).")

        max_items = cfg.max_items_per_source
        if items:
            for item in items[:max_items]:
                # 1. Classify notice title before fetching PDF or creating task
                cl_res = classify_notice(s.name, item.title, item.raw_text)
                if not cl_res.should_create_task:
                    classified_skipped += 1
                    continue

                src_items_classified_job += 1

                # Combine title, text, date
                item_text = f"TITLE: {item.title}\nURL: {item.url}\nRAW: {item.raw_text or ''}\n"
                
                # If PDF link exists, download smart pages politely
                if item.pdf_url:
                    pdf_text = fetcher.fetch_pdf_text(item.pdf_url, verify_ssl=s.verify_ssl)
                    if pdf_text:
                        item_text += f"\n--- PDF TEXT ---\n{pdf_text}"

                content_hash = hashlib.sha256(item_text.encode("utf-8")).hexdigest()[:16]
                if content_hash in known_hashes:
                    # Unchanged content -> skip
                    continue

                # Check if existing record in DB matches to attach for corrigenda/updates
                matched_id = store.find_matching_existing_id(s.name, item.notification_no or "", item.title)
                existing_record = store.get_job(matched_id) if matched_id else None

                tid, skip_reason = create_extraction_task(
                    source_name=s.name,
                    source_url=item.url or s.list_url,
                    notice_url=item.pdf_url,
                    notice_title=item.title,
                    category=s.category,
                    text_content=item_text,
                    org_level=s.level.value,
                    sector=s.sector,
                    state=s.state,
                    existing_job=existing_record,
                    kind=cl_res.kind,
                    include_old=include_old,
                )

                if tid is None and skip_reason == "likely_expired":
                    expired_skipped += 1
                    continue

                known_hashes.add(content_hash)
                known_hashes.add(tid)
                tasks_created += 1
                src_tasks_created += 1
                console.print(f"    [green]Created task:[/green] data/inbox/{tid}.json [{cl_res.kind}] '{item.title[:55]}'")
        else:
            # Fallback to whole page
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
            if content_hash not in known_hashes:
                tid, skip_reason = create_extraction_task(
                    source_name=s.name,
                    source_url=s.list_url,
                    notice_url=None,
                    notice_title=s.name,
                    category=s.category,
                    text_content=content,
                    org_level=s.level.value,
                    sector=s.sector,
                    state=s.state,
                    include_old=include_old,
                )
                if tid:
                    known_hashes.add(content_hash)
                    known_hashes.add(tid)
                    tasks_created += 1
                    src_tasks_created += 1
                    console.print(f"  [green]Created page task:[/green] data/inbox/{tid}.json")

        # Record successful source run
        store.record_source_run(
            source_name=s.name,
            run_at=src_run_at,
            fetch_ok=True,
            http_status=res.status_code,
            used_playwright=res.used_playwright,
            items_parsed=src_items_parsed,
            items_classified_job=src_items_classified_job,
            tasks_created=src_tasks_created,
            error=None,
        )

    console.print(f"\n[bold green]Update complete:[/bold green] {tasks_created} new task(s) created | {classified_skipped} non-jobs filtered | {expired_skipped} old notice(s) skipped.")

@app.command()
def coverage(
    psu: bool = typer.Option(False, "--psu", help="Display Central Public Sector Undertakings (PSU) coverage breakdown by Ratna status"),
):
    """Display category x state coverage grid or PSU coverage."""
    if psu:
        from govjobs.psu import render_psu_coverage_table
        render_psu_coverage_table(console)
    else:
        from govjobs.coverage import render_coverage_grid
        render_coverage_grid(console)

@app.command(name="psu-sync")
def psu_sync(
    wikipedia_url: str = typer.Option("https://en.wikipedia.org/wiki/List_of_public_sector_undertakings_in_India", "--url", help="Wikipedia PSU article URL"),
    overrides: str = typer.Option("psu_overrides.yaml", "--overrides", help="Path to manual overrides YAML"),
    output: str = typer.Option("psu_registry.yaml", "--output", help="Path to output psu_registry.yaml"),
):
    """Fetch Wikipedia PSU master list, normalize Ratna statuses, apply DPE overrides, and save psu_registry.yaml."""
    from govjobs.psu import sync_psu_registry
    console.print(f"[bold cyan]Synchronizing PSU Registry from Wikipedia and {overrides}...[/bold cyan]")
    try:
        psus, unrecognised = sync_psu_registry(
            wikipedia_url=wikipedia_url,
            overrides_file=overrides,
            output_file=output,
        )
        counts = {}
        for p in psus:
            r = p.get("ratna_class", "none")
            counts[r] = counts.get(r, 0) + 1

        console.print(f"[bold green]Successfully synced {len(psus)} PSUs to {output}:[/bold green]")
        console.print(f"  • Maharatna: {counts.get('maharatna', 0)}")
        console.print(f"  • Navratna: {counts.get('navratna', 0)}")
        console.print(f"  • Miniratna Category-I: {counts.get('miniratna_1', 0)}")
        console.print(f"  • Miniratna Category-II: {counts.get('miniratna_2', 0)}")
        console.print(f"  • Other / None: {counts.get('none', 0)}")

        if unrecognised:
            console.print(f"\n[bold yellow]Unrecognised Ratna labels ({len(unrecognised)}) for review:[/bold yellow]")
            for item in unrecognised[:10]:
                console.print(f"  [yellow]?[/yellow] {item}")
        else:
            console.print("  [dim]All Ratna labels cleanly normalized (0 unrecognised).[/dim]\n")
    except Exception as e:
        console.print(f"[bold red]Failed to sync PSU registry:[/bold red] {e}")
        raise typer.Exit(code=1)

@app.command()
def export(
    format: str = typer.Option("all", "--format", "-f", help="Export format: json, csv, html, all"),
    include_closed: bool = typer.Option(False, "--include-closed", help="Include closed notifications in export"),
):
    """Export stored jobs to JSON, CSV, and offline static HTML (excludes closed jobs by default)."""
    from govjobs.render import export_csv, export_html
    store = JobStore()
    all_jobs = store.get_all_jobs()
    fmt = format.lower()

    if fmt in ["json", "all"]:
        store.export_json("data/jobs.json", include_closed=include_closed)
        console.print("[green]Exported active jobs to data/jobs.json (closed archived in data/archive.json)[/green]")

    if fmt in ["csv", "all"]:
        export_csv(all_jobs, "data/jobs.csv", include_closed=include_closed)
        console.print("[green]Exported jobs to data/jobs.csv[/green]")

    if fmt in ["html", "all"]:
        export_html(all_jobs, "data/jobs.html", include_closed=include_closed)
        console.print("[green]Exported offline interactive HTML to data/jobs.html[/green]")

@app.command()
def add_url(url: str):
    """Create an extraction task for a missed notice page or PDF URL."""
    from govjobs.fetch import PoliteFetcher
    from govjobs.extract import create_extraction_task
    from govjobs.scrapers.pdf_notice import extract_pdf_from_url

    console.print(f"[bold cyan]Processing manual URL:[/bold cyan] {url}")
    if url.lower().endswith(".pdf"):
        text = extract_pdf_from_url(url)
        notice_url = url
    else:
        fetcher = PoliteFetcher()
        res = fetcher.fetch(url)
        if not res.ok:
            console.print(f"[red]Failed to fetch URL:[/red] {res.error}")
            raise typer.Exit(code=1)
        text = res.content
        notice_url = None

    if not text:
        console.print("[red]No content extracted from URL.[/red]")
        raise typer.Exit(code=1)

    tid = create_extraction_task(
        source_name="Manual Entry",
        source_url=url,
        notice_url=notice_url,
        text_content=text,
        org_level="other",
        sector="general",
    )
    console.print(f"[bold green]Task created:[/bold green] data/inbox/{tid}.json")

@app.command()
def tipoff(
    sources_file: str = typer.Option("tipoff_sources.yaml", "--sources", help="Tip-off sources YAML file"),
):
    """Politely discover engineering recruitment notices from job-news aggregators and feeds."""
    from govjobs.tipoff import run_tipoff
    console.print(f"[bold cyan]Scanning tip-off sources from {sources_file}...[/bold cyan]")
    created, skipped, logs = run_tipoff(tipoff_sources_file=sources_file)
    console.print(f"[bold green]Tip-off scan complete:[/bold green] {created} new tip(s) discovered | {skipped} non-engineering items filtered.")
    for l in logs[:10]:
        console.print(f"  • {l}")

@app.command()
def tips(
    status: str = typer.Option("new", "--status", help="Filter tips by status: new, resolved, dropped, all"),
):
    """List discovered recruitment tips waiting for resolution."""
    from govjobs.tipoff import get_all_tips
    st_filter = None if status.lower() == "all" else status.lower()
    tips_list = get_all_tips(status=st_filter)

    if not tips_list:
        console.print(f"[green]No tips found with status '{status}'.[/green]")
        return

    table = Table(title=f"Discovered Job-News Tips ({len(tips_list)} items)", show_header=True)
    table.add_column("Tip ID", style="bold cyan", width=14)
    table.add_column("Discovered (IST)", width=18)
    table.add_column("Site", style="dim", width=16)
    table.add_column("Matched PSU", style="bold green", width=22)
    table.add_column("Headline", width=40)
    table.add_column("Tip URL", style="blue")

    for t in tips_list:
        disc_at = fmt_datetime_ist(t.get("discovered_at"))
        table.add_row(
            t["id"][:12],
            disc_at,
            t.get("tip_site", "-")[:15],
            t.get("matched_psu") or "-",
            t.get("title", "-")[:38],
            t.get("tip_url", "-"),
        )

    console.print(table)
    console.print("\n[dim]To resolve a tip, find the official portal link and run: jobs tip-resolve <id> --url <official link>[/dim]")
    console.print("[dim]If no official link exists, run: jobs tip-resolve <id> --drop[/dim]\n")

@app.command(name="tip-resolve")
def tip_resolve_cmd(
    tip_id: str = typer.Argument(..., help="Tip ID to resolve"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="Official recruiter URL (.gov.in, .nic.in, or PSU portal)"),
    drop: bool = typer.Option(False, "--drop", help="Mark tip as dropped (no official link found)"),
):
    """Resolve a tip by supplying the official recruiter link or dropping it."""
    from govjobs.tipoff import resolve_tip
    success, msg = resolve_tip(tip_id, official_url=url, drop=drop)
    if success:
        console.print(f"[bold green]{msg}[/bold green]")
    else:
        console.print(f"[bold red]Failed to resolve tip:[/bold red] {msg}")
        raise typer.Exit(code=1)

@app.command()
def daily():
    """Daily pipeline runner: runs update, tipoff, export, then prints pending inbox and tips count."""
    console.print("[bold cyan]══════════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]       GovJobs Daily Pipeline Execution       [/bold cyan]")
    console.print("[bold cyan]══════════════════════════════════════════════[/bold cyan]\n")

    # 1. Update sources
    console.print("[bold]Step 1: Fetching official recruiter sources...[/bold]")
    try:
        update()
    except Exception as e:
        console.print(f"[yellow]Update completed with notices:[/yellow] {e}")

    # 2. Tip-off discovery
    console.print("\n[bold]Step 2: Scanning job-news tip-off feeds...[/bold]")
    try:
        from govjobs.tipoff import run_tipoff
        c, s, logs = run_tipoff()
        console.print(f"Discovered {c} new tip(s) ({s} non-engineering items filtered).")
    except Exception as e:
        console.print(f"[yellow]Tipoff scan notice:[/yellow] {e}")

    # 3. Export active jobs
    console.print("\n[bold]Step 3: Exporting fresh JSON, CSV, and HTML...[/bold]")
    try:
        export(format="all", include_closed=False)
    except Exception as e:
        console.print(f"[yellow]Export notice:[/yellow] {e}")

    # 4. Summary for the AI extraction agent
    inbox_p = Path("data/inbox")
    inbox_cnt = len(list(inbox_p.glob("*.json"))) if inbox_p.exists() else 0
    from govjobs.tipoff import get_all_tips
    new_tips = get_all_tips(status="new")

    console.print("\n[bold green]══════════════════════════════════════════════[/bold green]")
    console.print(f"[bold green]Daily Run Complete:[/bold green]")
    console.print(f"  • Inbox tasks waiting for extraction: [bold yellow]{inbox_cnt}[/bold yellow]  (Run: 'jobs extract')")
    console.print(f"  • Tips waiting for recruiter resolution: [bold yellow]{len(new_tips)}[/bold yellow]  (Run: 'jobs tips')")
    console.print("[bold green]══════════════════════════════════════════════[/bold green]\n")

if __name__ == "__main__":
    app()
