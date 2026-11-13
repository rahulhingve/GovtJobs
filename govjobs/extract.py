import hashlib
import json
import logging
import re
import shutil
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from pydantic import ValidationError
from govjobs.models import Job, AgentJob, Branch, Level, QualificationType, EmploymentType, generate_job_id
from govjobs.store import JobStore
from govjobs.utils import get_ist_today, parse_to_iso_date

logger = logging.getLogger("govjobs.extract")
IST = timezone(timedelta(hours=5, minutes=30))

BRANCH_KEYWORDS = {
    Branch.CSE: [r"\bcomputer\s+science\b", r"\bcomp(?:uter)?\s*\.?\s*sc(?:ience)?\b", r"\bcse\b", r"\bcs\b"],
    Branch.IT: [r"\binformation\s+technology\b", r"\bit\b"],
    Branch.ECE: [r"\belectronics\s*(?:&|and)\s*comm(?:unication)?\b", r"\bece\b", r"\be\s*&\s*c\b"],
    Branch.EEE: [r"\belectrical\s*(?:&|and)\s*electronics\b", r"\belectrical\s+eng(?:ineering)?\b", r"\beee\b", r"\bee\b"],
    Branch.INSTRU: [r"\binstrumentation\b", r"\belectronics\s*&\s*instru(?:mentation)?\b", r"\be&i\b", r"\binstru\b"],
    Branch.ME: [r"\bmechanical\s+eng(?:ineering)?\b", r"\bmech\b", r"\bme\b"],
    Branch.CE: [r"\bcivil\s+eng(?:ineering)?\b", r"\bcivil\b", r"\bce\b"],
    Branch.CHE: [r"\bchemical\s+eng(?:ineering)?\b", r"\bchemical\b", r"\bche\b"],
    Branch.MIN: [r"\bmining\s+eng(?:ineering)?\b", r"\bmining\b"],
    Branch.MET: [r"\bmetallurg(?:y|ical)\b", r"\bmaterials\s+eng\b"],
    Branch.PETRO: [r"\bpetroleum\b", r"\bpetrochemical\b"],
    Branch.PROD: [r"\bproduction\s+eng(?:ineering)?\b", r"\bindustrial\s+eng(?:ineering)?\b"],
    Branch.AERO: [r"\baeronautical\b", r"\baerospace\b"],
    Branch.MARINE: [r"\bmarine\s+eng(?:ineering)?\b", r"\bnaval\s+architecture\b"],
    Branch.AUTO: [r"\bautomobile\b", r"\bautomotive\b"],
    Branch.BIO: [r"\bbiotechnology\b", r"\bbiomedical\b"],
    Branch.ALL: [r"\bany\s+engineering\s+discipline\b", r"\ball\s+engineering\s+branches\b", r"\bengineering\s+degree\s+in\s+any\s+discipline\b"],
}

def map_branches_from_text(text: str) -> List[Branch]:
    """Map natural language text to normalized Branch enum values."""
    found: List[Branch] = []
    text_lower = text.lower()
    for branch, patterns in BRANCH_KEYWORDS.items():
        for pat in patterns:
            if re.search(pat, text_lower):
                if branch not in found:
                    found.append(branch)
                break
    if not found:
        if re.search(r"\bb\.?tech\b|\bb\.?e\b|\bengineering\s+degree\b", text_lower):
            found.append(Branch.OTHER)
    return found

def extract_rule_hints(text: str) -> Dict[str, Any]:
    hints: Dict[str, Any] = {
        "dates_found": [],
        "iso_dates": [],
        "btech_keywords": [],
        "gate_detected": False,
        "vacancies_hint": None,
    }

    # Date pattern: DD/MM/YYYY, DD.MM.YYYY, DD-MM-YYYY
    date_matches = re.finditer(r"\b(\d{1,2})[/\.-](\d{1,2})[/\.-](\d{4})\b", text)
    for m in date_matches:
        raw_str = m.group(0)
        d, mo, y = m.group(1), m.group(2), m.group(3)
        if raw_str not in hints["dates_found"]:
            hints["dates_found"].append(raw_str)
        try:
            dt = datetime.strptime(f"{y}-{mo.zfill(2)}-{d.zfill(2)}", "%Y-%m-%d")
            iso_str = dt.strftime("%Y-%m-%d")
            if iso_str not in hints["iso_dates"]:
                hints["iso_dates"].append(iso_str)
        except ValueError:
            pass

    # BTech / BE keywords
    btech_matches = re.findall(r"\b(B\.?Tech|B\.?E\.?|Bachelor\s+of\s+Technology|Bachelor\s+of\s+Engineering)\b", text, re.IGNORECASE)
    hints["btech_keywords"] = list(set([m.strip() for m in btech_matches]))

    # GATE
    if re.search(r"\bGATE\b", text):
        hints["gate_detected"] = True

    # Vacancies
    vac_match = re.search(r"\b(\d+)\s+(?:vacancies|posts|openings|seats)\b", text, re.IGNORECASE)
    if vac_match:
        try:
            hints["vacancies_hint"] = int(vac_match.group(1))
        except ValueError:
            pass

    return hints

def check_likely_expired(iso_dates: List[str], today: Optional[date] = None) -> bool:
    """If notice text contains dates and ALL of them are before today, mark likely expired."""
    if not iso_dates:
        return False
    if today is None:
        today = get_ist_today()
    parsed_dates = []
    for d in iso_dates:
        try:
            parsed_dates.append(datetime.strptime(d, "%Y-%m-%d").date())
        except ValueError:
            pass
    if parsed_dates and all(d < today for d in parsed_dates):
        return True
    return False

def create_extraction_task(
    source_name: str,
    source_url: str,
    notice_url: Optional[str],
    text_content: str,
    org_level: str,
    sector: str,
    category: Optional[str] = None,
    notice_title: Optional[str] = None,
    state: Optional[str] = None,
    existing_job: Optional[Job] = None,
    kind: str = "new",
    include_old: bool = False,
    inbox_dir: str = "data/inbox"
) -> Tuple[Optional[str], Optional[str]]:
    """
    Write a task file to data/inbox/<task_id>.json.
    Returns (task_id, reason). If skipped due to expiry, returns (None, "likely_expired").
    """
    inbox_path = Path(inbox_dir)
    inbox_path.mkdir(parents=True, exist_ok=True)

    hints = extract_rule_hints(text_content)
    is_old = check_likely_expired(hints["iso_dates"])
    if is_old and not include_old:
        return None, "likely_expired"

    content_hash = hashlib.sha256(text_content.encode("utf-8")).hexdigest()[:16]
    task_id = f"{content_hash}"
    task_file = inbox_path / f"{task_id}.json"

    mapped_branches = [b.value for b in map_branches_from_text(text_content)]

    task_payload = {
        "task_id": task_id,
        "source_name": source_name,
        "source_url": source_url,
        "notice_url": notice_url,
        "notice_title": notice_title or title_fallback(text_content),
        "category": category or "Central exams and boards",
        "level": org_level,
        "sector": sector,
        "state": state,
        "kind": kind,
        "likely_expired": is_old,
        "content_hash": content_hash,
        "created_at": datetime.now(IST).isoformat(),
        "rule_hints": hints,
        "suggested_branches": mapped_branches,
        "notice_text": text_content[:15000],
        "existing_record": existing_job.model_dump() if existing_job else None
    }

    task_file.write_text(json.dumps(task_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Created extraction task {task_id} in {task_file}")
    return task_id, None

def title_fallback(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        return lines[0].replace("TITLE:", "").strip()[:80]
    return "Recruitment Notice"

def clean_inbox(
    inbox_dir: str = "data/inbox",
    done_dir: str = "data/done",
    rejected_dir: str = "data/rejected",
    outbox_dir: str = "data/outbox",
) -> int:
    """Remove tasks from data/inbox/ that have already been processed in done, done/tasks, rejected, or outbox."""
    inbox_p = Path(inbox_dir)
    if not inbox_p.exists():
        return 0

    known_stems = set()
    for folder in [done_dir, f"{done_dir}/tasks", rejected_dir, outbox_dir]:
        fp = Path(folder)
        if fp.exists():
            for f in fp.glob("*.json"):
                known_stems.add(f.stem)

    removed = 0
    for task_file in inbox_p.glob("*.json"):
        if task_file.stem in known_stems:
            task_file.unlink()
            removed += 1
    return removed

def ingest_outbox(
    outbox_dir: str = "data/outbox",
    done_dir: str = "data/done",
    rejected_dir: str = "data/rejected",
    inbox_dir: str = "data/inbox",
    store: Optional[JobStore] = None
) -> Tuple[int, int, List[str]]:
    """
    Validate every file in data/outbox/.
    Supports:
    - Skip protocol: {"skip": true, "reason": "..."}
    - AgentJob / Job extraction output:
      Always overwrites id with generate_job_id(org, notification_no or notice_title, post_title),
      and sets first_seen, last_seen, content_hash, URLs, level, sector, state, category from task.
    - Moves processed inbox task to data/done/tasks/
    """
    outbox_path = Path(outbox_dir)
    done_path = Path(done_dir)
    done_tasks_path = done_path / "tasks"
    rejected_path = Path(rejected_dir)
    inbox_path = Path(inbox_dir)

    done_path.mkdir(parents=True, exist_ok=True)
    done_tasks_path.mkdir(parents=True, exist_ok=True)
    rejected_path.mkdir(parents=True, exist_ok=True)

    if store is None:
        store = JobStore()

    valid_count = 0
    rejected_count = 0
    messages: List[str] = []

    if not outbox_path.exists():
        return 0, 0, ["Outbox directory does not exist."]

    task_files = list(outbox_path.glob("*.json"))
    if not task_files:
        return 0, 0, ["No files in outbox."]

    now_iso = datetime.now(IST).isoformat()

    for out_file in task_files:
        task_id = out_file.stem
        inbox_task_file = inbox_path / f"{task_id}.json"
        task_data = {}
        if inbox_task_file.exists():
            try:
                task_data = json.loads(inbox_task_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        try:
            raw_content = out_file.read_text(encoding="utf-8")
            data = json.loads(raw_content)

            # Check Skip Protocol
            if isinstance(data, dict) and data.get("skip") is True:
                reason = data.get("reason", "No reason provided")
                messages.append(f"Skipped {out_file.name}: {reason}")
                # Move outbox file to done
                shutil.move(str(out_file), str(done_path / out_file.name))
                # Move inbox task to done/tasks
                if inbox_task_file.exists():
                    shutil.move(str(inbox_task_file), str(done_tasks_path / inbox_task_file.name))
                continue

            # Process Job objects or AgentJob objects
            raw_items = data if isinstance(data, list) else [data]
            jobs_to_save: List[Job] = []

            for item in raw_items:
                # Validate agent input via AgentJob
                agent_job = AgentJob(**item)
                
                # Derive or use task metadata
                org = agent_job.org
                post_title = agent_job.post_title
                notif_no = agent_job.notification_no or ""
                notice_title = task_data.get("notice_title") or notif_no or post_title
                
                # ENFORCE STABLE HASH ID
                stable_id = generate_job_id(org, notif_no or notice_title, post_title)
                
                job_dict = agent_job.model_dump()
                job_dict["id"] = stable_id
                job_dict["level"] = Level(task_data.get("level", "other"))
                job_dict["sector"] = task_data.get("sector", "general")
                job_dict["state"] = task_data.get("state")
                job_dict["category"] = task_data.get("category", "PSUs and CPSEs" if job_dict["level"] == Level.PSU else "Central exams and boards")
                job_dict["source_url"] = task_data.get("source_url") or item.get("source_url") or "https://example.gov.in"
                job_dict["notice_url"] = task_data.get("notice_url") or item.get("notice_url")
                job_dict["content_hash"] = task_data.get("content_hash") or task_id
                job_dict["first_seen"] = task_data.get("created_at") or now_iso
                job_dict["last_seen"] = now_iso

                # PSU registry auto-population
                try:
                    from govjobs.psu import find_psu_match
                    psu_info = find_psu_match(org)
                    if psu_info:
                        job_dict["psu_name"] = psu_info["name"]
                        job_dict["psu_class"] = psu_info["ratna_class"]
                        if psu_info.get("ministry"):
                            job_dict["ministry"] = psu_info["ministry"]
                        if psu_info.get("ratna_class") != "none":
                            job_dict["category"] = "PSUs and CPSEs"
                            job_dict["level"] = Level.PSU
                except Exception:
                    pass

                full_job = Job(**job_dict)
                jobs_to_save.append(full_job)

            # Save valid jobs to database
            for job in jobs_to_save:
                job_id, is_new = store.upsert_job(job)
                action = "Inserted" if is_new else "Updated"
                messages.append(f"{action} job {job_id} ({job.org} - {job.post_title})")
                valid_count += 1

            # Move outbox file to done
            shutil.move(str(out_file), str(done_path / out_file.name))
            # Move inbox task to done/tasks
            if inbox_task_file.exists():
                shutil.move(str(inbox_task_file), str(done_tasks_path / inbox_task_file.name))

        except (ValidationError, Exception) as e:
            rejected_count += 1
            err_msg = str(e)
            messages.append(f"Rejected {out_file.name}: {err_msg}")
            
            # Move to rejected and write error details
            shutil.move(str(out_file), str(rejected_path / out_file.name))
            err_file = rejected_path / f"{out_file.stem}.error.txt"
            err_file.write_text(err_msg, encoding="utf-8")

    return valid_count, rejected_count, messages
