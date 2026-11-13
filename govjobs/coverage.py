from typing import Dict, List, Set
from rich.console import Console
from rich.table import Table

from govjobs.registry import load_sources, VALID_CATEGORIES
from govjobs.store import JobStore

# Indian States and Union Territories (28 States + 8 UTs)
INDIAN_STATES_AND_UTS = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand",
    "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur",
    "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal",
    # UTs
    "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry"
]

def render_coverage_grid(console: Console, sources_file: str = "sources.yaml"):
    """
    Render category x state coverage grid showing enabled, healthy, and missing sources.
    """
    sources = load_sources(sources_file)
    store = JobStore()
    all_jobs = store.get_all_jobs()

    # Tally sources by category and state
    grid: Dict[str, Dict[str, int]] = {cat: {} for cat in VALID_CATEGORIES}
    
    for s in sources:
        cat = s.category
        if cat not in grid:
            grid[cat] = {}
        st = s.state or "Central/All-India"
        grid[cat][st] = grid[cat].get(st, 0) + 1

    table = Table(title="India-wide BTech Govt Jobs Recruitment Coverage Grid", show_header=True)
    table.add_column("Recruitment Category", style="bold cyan", width=32)
    table.add_column("Covered States / Units", style="green", width=25)
    table.add_column("Sources Registered", width=20)
    table.add_column("Jobs Stored", width=12)
    table.add_column("Target Scope", style="dim")

    for cat in VALID_CATEGORIES:
        covered = grid.get(cat, {})
        num_sources = sum(covered.values())
        cat_jobs = sum(1 for j in all_jobs if (j.category or "").strip().lower() == cat.strip().lower())

        if covered:
            states_str = ", ".join(covered.keys())
            status_style = "[green]Active[/green]" if num_sources > 0 else "[yellow]Partial[/yellow]"
        else:
            states_str = "[dim]None yet[/dim]"
            status_style = "[red]Missing[/red]"

        table.add_row(
            cat,
            states_str[:25],
            f"{num_sources} ({status_style})",
            str(cat_jobs),
            "All India / 36 States & UTs" if "State" in cat else "National / All Units"
        )

    console.print(table)
    console.print("\n[dim]Target: Complete coverage of all 28 States, 8 UTs, Central Boards, PSUs, and Defence bodies.[/dim]\n")
